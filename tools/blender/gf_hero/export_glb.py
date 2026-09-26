"""Stage 5: export a hero, or a chassis weapon built by the gf_hero chain, to its shipped GLB (headless Blender 5.2).

  blender -b --python-exit-code 1 art/characters/brax/production/brax_anim.blend -P tools/blender/gf_hero/export_glb.py -- --key brax
  blender -b --python-exit-code 1 art/weapons/anvil_gauntlets/production/anvil_gauntlets_stage2.blend \
          -P tools/blender/gf_hero/export_glb.py -- --weapon anvil_gauntlets
  (without a .blend on the command line the script opens the default file named above; nothing is saved to it)

--key <hero>: the rigged + animated stage-4 file -> assets/models/characters/<key>.glb + <key>.meta.json
  1. Blender-side checks before anything is written: the GF_Hero_v1 hierarchy (gf_hero_rig.validate_hierarchy), per body
     part the skin weights (unweighted vertices, > 4 influences, sums != 1, weight on root / sockets, vertex groups that
     are not bones), closed surfaces, one UV map, the triangle budget (<= 25k), the material's base colour / emissive /
     normal textures (<= 2048 px), and the NLA tracks against reports/anim/clips.json and required_clips.json;
  2. in memory only: the body parts are joined into one skinned mesh <key>_mesh (one draw call, one material), the
     GF_ValidationPoses track is dropped and the clip tracks unmuted, the material goes single-sided when every part is
     closed;
  3. glTF binary, +Y up, deform bones only (the 63 GF_Hero_v1 bones: core, twist, fingers, sockets), 4 influences, every
     NLA track baked as one named animation sampled at 30 fps (the twist constraints are baked), textures embedded as
     PNG, tangents, NO vertex colours (Bevy multiplies the base colour by COLOR_0), no Draco / meshopt / quantisation
     (bevy_gltf 0.20 supports none of them);
  4. read back: validate_glb.validate_hero (the stdlib gate CI runs) and a source-fidelity check - for every clip at its
     first, middle and last frame, every joint's world matrix from the GLB's own forward kinematics must equal the
     Blender pose bone (converted to +Y up) within 1e-4;
  5. the sidecar <key>.meta.json {skeleton, clips, clip_info (frames, loop, layer, events, design speed, weapon variant
     swaps), sockets, tris, textures, weapon, status: ai_final_pending_user_approval, sha256}, then the gate again with
     the sidecar; the report goes to art/characters/<key>/reports/export_report.json (section "hero"). When the
     default weapon's GLB has no offhand node and no _fist_ / _open_ variants (a sleeve weapon such as Valdris's
     colossus_cannon, built by the weapon track), clip_info.<clip>.weapon_variant is null, the hands' fist / open
     frames move to clip_info.<clip>.hand_pose, and weapon.attach says it rides weapon_R alone.
--weapon <chassis>: the stage-2 weapon file (open + fist variants per hand, authored in the socket grip frame) ->
  assets/models/weapons/<chassis>.glb + .meta.json in the docs/art/WEAPONS.md layout: root <chassis> = the right grip
  frame; <chassis>_fist_R / <chassis>_open_R, grip_R, muzzle, glow_core under it; offhand (the left pair, re-parented by
  the client to weapon_L with an identity transform) holding <chassis>_fist_L / <chassis>_open_L and muzzle_2, with
  grip_L on its origin. Checked like the hero (budget, textures, no vertex colours) and with the armory's
  tools/blender/gf_assets/gfa_validate.py (reported, read only). Report: section "weapons.<chassis>" of the designing
  hero's export_report.json.
Exit code 1 when a check fails (the files are still written, with validation.ok false, so they can be inspected).
"""
import datetime
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import validate_glb as V  # noqa: E402
from s2lib import log, rel, script_args, write_json  # noqa: E402

ROOT = V.ROOT
argv = script_args(__doc__)


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


KEY = opt("--key")
WEAPON = opt("--weapon")
if not KEY and not WEAPON:
    raise SystemExit(__doc__)
TODAY = datetime.date.today().isoformat()
C = Matrix(R.SOCKET_TO_GRIP)                 # Blender (x, y, z) -> glTF (x, z, -y)
MAX_TEX = 2048
EXPORT_COMMON = dict(
    export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
    export_texcoords=True, export_normals=True, export_tangents=True, export_materials="EXPORT",
    export_image_format="AUTO", export_vertex_color="NONE", export_all_vertex_colors=False,
    export_active_vertex_color_when_no_material=False, export_attributes=False,
    export_cameras=False, export_lights=False, export_extras=False, export_morph=False,
    export_draco_mesh_compression_enable=False, export_meshopt_compression_enable=False, export_use_gltfpack=False,
    export_gpu_instances=False, export_leaf_bone=False)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update_report(key, section, data, sub=None):
    """Merge one section into art/characters/<key>/reports/export_report.json (other tools own the other sections)."""
    p = os.path.join(ROOT, "art", "characters", key, "reports", "export_report.json")
    rep = {}
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            rep = json.load(f)
    rep["hero"] = key
    rep["stage"] = "5_export_validate"
    rep["updated"] = TODAY
    if sub:
        rep.setdefault(section, {})[sub] = data
    else:
        rep[section] = data
    oks = [v.get("ok") for k, v in rep.items() if isinstance(v, dict) and "ok" in v]
    oks += [v.get("ok") for v in rep.get("weapons", {}).values() if isinstance(v, dict)]
    rep["ok"] = all(o is True for o in oks) if oks else False
    write_json(p, rep)
    return p


def open_file(default):
    cur = os.path.normcase(os.path.abspath(bpy.data.filepath)) if bpy.data.filepath else ""
    if cur != os.path.normcase(os.path.abspath(default)):
        bpy.ops.wm.open_mainfile(filepath=default)
    log("source", rel(bpy.data.filepath))


def select(objs, active):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.hide_viewport = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def surface_stats(me):
    ei = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("edge_index", ei)
    cnt = np.bincount(ei, minlength=len(me.edges))
    return {"verts": len(me.vertices), "tris": sum(len(p.vertices) - 2 for p in me.polygons),
            "boundary_edges": int((cnt == 1).sum()), "nonmanifold_edges": int((cnt > 2).sum()),
            "uv_layers": [u.name for u in me.uv_layers],
            "color_attributes": [a.name for a in me.color_attributes]}


def material_images(mat):
    out = []
    if mat and mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                out.append({"name": n.image.name, "px": list(n.image.size), "colorspace": n.image.colorspace_settings.name,
                            "file": n.image.filepath})
    return out


# =====================================================================================================================
# the hero
# =====================================================================================================================

def hero_blender_checks(arm, parts, man, spec, errors):
    chk = {"hierarchy_problems": R.validate_hierarchy(arm), "parts": {}}
    errors += ["hierarchy: %s" % p for p in chk["hierarchy_problems"]]
    bones = {b.name: b for b in arm.data.bones}
    deform = {n for n, b in bones.items() if b.use_deform}
    no_weight = set(R.non_weight_bone_names())
    tris = 0
    uv_names = set()
    mats = set()
    for o in parts:
        me = o.data
        st = surface_stats(me)
        tris += st["tris"]
        uv_names |= set(st["uv_layers"])
        gname = {vg.index: vg.name for vg in o.vertex_groups}
        st["non_bone_groups"] = sorted(n for n in gname.values() if n not in bones)
        unw = over = nonnorm = onbad = 0
        maxerr = 0.0
        for v in me.vertices:
            ws = [(gname[g.group], g.weight) for g in v.groups if g.weight > 0.0 and gname.get(g.group) in deform]
            if not ws:
                unw += 1
                continue
            if len(ws) > 4:
                over += 1
            e = abs(sum(w for _n, w in ws) - 1.0)
            maxerr = max(maxerr, e)
            if e > 1e-3:
                nonnorm += 1
            if any(n in no_weight and w > 1e-3 for n, w in ws):
                onbad += 1
        st.update(unweighted=unw, over_4_influences=over, not_normalized=nonnorm, weight_sum_max_error=round(maxerr, 7),
                  on_root_or_socket=onbad,
                  armature_modifier=any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers),
                  materials=[m.name for m in me.materials if m])
        mats |= set(st["materials"])
        chk["parts"][o.name] = st
        for k, what in (("unweighted", "unweighted vertices"), ("over_4_influences", "vertices with > 4 influences"),
                        ("not_normalized", "vertices whose weights do not sum to 1"),
                        ("on_root_or_socket", "vertices weighted to root or a socket")):
            if st[k]:
                errors.append("%s: %d %s" % (o.name, st[k], what))
        if not st["armature_modifier"]:
            errors.append("%s has no Armature modifier on %s" % (o.name, R.RIG_NAME))
        if len(st["uv_layers"]) != 1:
            errors.append("%s has UV maps %s (exactly one expected)" % (o.name, st["uv_layers"]))
    chk["tris"] = tris
    chk["closed"] = all(st["boundary_edges"] == 0 and st["nonmanifold_edges"] == 0 for st in chk["parts"].values())
    if tris > V.MAX_TRIS:
        errors.append("the body set has %d triangles > %d" % (tris, V.MAX_TRIS))
    if len(uv_names) != 1:
        errors.append("the parts use different UV map names %s (the join would split TEXCOORD sets)" % sorted(uv_names))
    if len(mats) != 1:
        errors.append("the parts use materials %s (one hero material expected)" % sorted(mats))
    mat = bpy.data.materials.get(sorted(mats)[0]) if mats else None
    imgs = material_images(mat)
    chk["material"] = {"name": mat.name if mat else None, "images": imgs}
    kinds = {k: any(k in i["name"] for i in imgs) for k in ("basecolor", "emissive", "normal")}
    for k, ok in kinds.items():
        if not ok:
            errors.append("material %s has no %s texture" % (mat.name if mat else None, k))
    for i in imgs:
        if max(i["px"]) > MAX_TEX:
            errors.append("texture %s is %s > %d px" % (i["name"], i["px"], MAX_TEX))
    tracks = [t.name for t in arm.animation_data.nla_tracks] if arm.animation_data else []
    want = [man["clips"][c]["action"] for c in man["order"]]
    req = V.required_clip_names(spec, KEY) or {}
    chk["nla_tracks"] = {"hero_tracks": len([t for t in tracks if t.startswith(KEY + "_")]),
                         "missing_vs_clips_json": [a for a in want if a not in tracks],
                         "missing_vs_required_clips": [a for a in req if a not in tracks],
                         "not_exported": [t for t in tracks if not t.startswith(KEY + "_")]}
    if chk["nla_tracks"]["missing_vs_clips_json"] or chk["nla_tracks"]["missing_vs_required_clips"]:
        errors.append("NLA tracks missing: %s" % sorted(set(chk["nla_tracks"]["missing_vs_clips_json"] + chk["nla_tracks"]["missing_vs_required_clips"])))
    return chk, mat


def source_fidelity(glb, arm, man, scene):
    """Every joint's world matrix in the GLB (its own FK) against the Blender pose bone, per clip at 3 frames."""
    g = V.Glb(glb)
    anims = {a["name"]: a for a in g.doc.get("animations", [])}
    names = g.names
    bones = [b.name for b in arm.data.bones if b.use_deform]
    idx = {b: names.index(b) for b in bones if b in names}
    for tr in arm.animation_data.nla_tracks:
        tr.mute = True
    out, worst = {}, 0.0
    for clip in man["order"]:
        info = man["clips"][clip]
        act = bpy.data.actions[info["action"]]
        arm.animation_data.action = act
        if act.slots:
            arm.animation_data.action_slot = act.slots[0]
        a = anims.get(info["action"])
        if a is None:
            out[info["action"]] = None
            continue
        chans = V.channel_data(g, a)
        errs = []
        for f in sorted({0, info["frames"] // 2, info["frames"]}):
            scene.frame_set(f)
            wm = V.world_matrices(g, V.sample_animation(g, a, f / float(V.FPS), chans))
            e = 0.0
            for b, i in idx.items():
                B = C @ arm.matrix_world @ arm.pose.bones[b].matrix
                G = wm[i]
                e = max(e, max(abs(B[r][c] - G[r][c]) for r in range(3) for c in range(4)))
            errs.append(e)
        out[info["action"]] = max(errs)
        worst = max(worst, max(errs))
    arm.animation_data.action = None
    return {"frames_per_clip": "first, middle, last", "joints": len(idx), "max_error": worst, "per_clip": out,
            "ok": worst < 1e-4 and all(v is not None for v in out.values())}


def export_hero():
    A = os.path.join(ROOT, "art", "characters", KEY)
    src = os.path.join(A, "production", "%s_anim.blend" % KEY)
    open_file(src)
    scene = bpy.context.scene
    scene.render.fps = V.FPS
    scene.render.fps_base = 1.0
    with open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8") as f:
        man = json.load(f)
    with open(os.path.join(A, "status.json"), encoding="utf-8") as f:
        status = json.load(f)
    spec = V.load_spec()
    errors = []
    arm = bpy.data.objects[R.RIG_NAME]
    parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm and not o.name.startswith("PREVIEW_")]
    log("parts:", [o.name for o in parts])
    chk, mat = hero_blender_checks(arm, parts, man, spec, errors)
    log("Blender checks: %d tris, closed %s, %d problem(s)" % (chk["tris"], chk["closed"], len(errors)))

    # ---- prepare (in memory; the .blend is never saved) ----
    arm.animation_data.action = None
    for tr in list(arm.animation_data.nla_tracks):
        if tr.name.startswith(KEY + "_"):
            tr.mute = False
        else:
            arm.animation_data.nla_tracks.remove(tr)
    for pb in arm.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    body = max(parts, key=lambda o: len(o.data.vertices))
    select(parts, body)
    with bpy.context.temp_override(active_object=body, selected_editable_objects=parts, selected_objects=parts):
        bpy.ops.object.join()
    mesh_ob = body
    mesh_ob.name = "%s_mesh" % KEY
    mesh_ob.data.name = "%s_mesh" % KEY
    for ca in list(mesh_ob.data.color_attributes):      # paint masks (gf_mask / src_col) never ship
        mesh_ob.data.color_attributes.remove(ca)
    if mat is not None:
        mat.use_backface_culling = bool(chk["closed"])
    joined_tris = sum(len(p.vertices) - 2 for p in mesh_ob.data.polygons)
    log("joined into %s: %d verts, %d tris; material single-sided: %s" % (mesh_ob.name, len(mesh_ob.data.vertices), joined_tris, chk["closed"]))

    out_dir = os.path.join(ROOT, "assets", "models", "characters")
    os.makedirs(out_dir, exist_ok=True)
    glb = os.path.join(out_dir, "%s.glb" % KEY)
    select([arm, mesh_ob], arm)
    settings = dict(EXPORT_COMMON, export_skins=True, export_influence_nb=4, export_all_influences=False,
                    export_def_bones=True, export_rest_position_armature=True, export_armature_object_remove=False,
                    export_hierarchy_flatten_bones=False, export_animations=True, export_animation_mode="NLA_TRACKS",
                    export_force_sampling=True, export_frame_step=1, export_optimize_animation_size=False,
                    export_anim_single_armature=True, export_reset_pose_bones=True, export_anim_slide_to_zero=False,
                    export_pointer_animation=False,
                    export_copyright="GODFORGE. Body topology from the MakeHuman hm08 base mesh (CC0).")
    bpy.ops.export_scene.gltf(filepath=glb, **settings)
    log("wrote %s (%.2f MB)" % (rel(glb), os.path.getsize(glb) / 1e6))

    # ---- read back ----
    rep0 = V.validate_hero(glb, meta=None, spec=spec)
    fid = source_fidelity(glb, arm, man, scene)
    log("source fidelity: max joint matrix error %.2e over %d clips" % (fid["max_error"], len(fid["per_clip"])))
    if not fid["ok"]:
        errors.append("the GLB's clips differ from the Blender source (max %.2e)" % fid["max_error"])

    # ---- sidecar ----
    wkey = (status.get("signature_weapon") or {}).get("chassis")
    wglb = "assets/models/weapons/%s.glb" % wkey if wkey else None
    # the weapon's layout, when its GLB is there: a sleeve weapon without an offhand node or hand variants (Valdris's
    # colossus_cannon, built by the weapon track) rides weapon_R alone, and the hands' fist / open poses are the hero's
    # own keyed fingers, not weapon swaps (Brax's anvil_gauntlets have both, so his sidecar is unchanged)
    wnames = V.Glb(os.path.join(ROOT, wglb)).names if wglb and os.path.isfile(os.path.join(ROOT, wglb)) else None
    sleeve_only = wnames is not None and "offhand" not in wnames and not any(
        n.endswith(("_fist_R", "_open_R", "_fist_L", "_open_L")) for n in wnames)
    clip_info = {}
    for clip in man["order"]:
        c = man["clips"][clip]
        clip_info[c["action"]] = {
            "clip": clip, "family": c["family"], "loop": c["loop"], "layer": c["layer"], "frames": c["frames"],
            "duration_s": round(c["frames"] / float(V.FPS), 5), "fps": V.FPS,
            "events": {k: {"frame": int(v), "time_s": round(int(v) / float(V.FPS), 5)}
                       for k, v in sorted(c.get("events", {}).items(), key=lambda kv: kv[1])},
            "design_speed_mps": c.get("design_speed_mps"), "travel_mps": c.get("travel_mps"),
            "slide_exempt": c.get("slide_exempt", False),
            "weapon_variant": c.get("metrics", {}).get("weapon_variant"),
            "maps_to": c.get("maps_to"), "purpose": c.get("purpose")}
        if sleeve_only:
            clip_info[c["action"]]["hand_pose"] = clip_info[c["action"]]["weapon_variant"]
            clip_info[c["action"]]["weapon_variant"] = None
    meta = {
        "kind": "character", "key": KEY, "name": status.get("name"),
        "skeleton": "%s v%d" % (R.RIG_NAME, R.CONTRACT_VERSION), "armature": R.RIG_NAME,
        "joints": rep0.get("joints"), "extra_bones": rep0.get("extra_bones", []),
        "tris": rep0.get("tris"), "tris_budget": [V.MIN_TRIS, V.MAX_TRIS],
        "textures": rep0.get("textures"), "material": (rep0.get("materials") or [None])[0],
        "sockets": rep0.get("sockets"),
        "clips": [man["clips"][c]["action"] for c in man["order"]],
        "clip_info": clip_info,
        "playback": {
            "fps": V.FPS,
            "naming": "<key>_<clip>, loops <key>_<clip>@loop (docs/art/GF_HERO_SKELETON.md section 8)",
            "locomotion": "playback rate = ground speed / clip_info.design_speed_mps (walk, run, strafe_*, backpedal)",
            "upper_layer": "layer 'upper' clips: mask spine_01 and its children over locomotion; their first and last frames are %s_idle_combat@loop frame 0" % KEY,
            "events": "glTF has no events: clip_info.<clip>.events gives the frame and time of each (30 fps)",
            "weapon_variant": "clip_info.<clip>.weapon_variant: per hand, the sleeve weapon's start variant (fist/open) and the frames where it swaps",
            "in_place": "only pelvis translates; the entity moves in the sim"},
        "weapon": {"default": wkey, "glb": wglb,
                   "attach": "weapon scene = identity child of weapon_R; its offhand node re-parented to weapon_L with an identity transform"} if wkey else None,
        "status": "ai_final_pending_user_approval",
        "axes": "glTF +Y up, 1 unit = 1 m. The hero faces +Z, origin on the ground between the feet, rest pose = T-pose. "
                "Socket nodes: -Z = forward (grip +Y), +Y = up, +X = right; a weapon scene attaches as an identity child.",
        "bounds_m": rep0.get("bounds_m"), "height_m": rep0.get("height_m"),
        "glb": rel(glb), "glb_bytes": os.path.getsize(glb), "glb_sha256": sha256(glb),
        "source_blend": rel(src), "build_script": "tools/blender/gf_hero/export_glb.py",
        "pipeline": "docs/ART_PIPELINE.md stage 5", "generator": "Blender %s" % bpy.app.version_string,
        "built": TODAY,
        "validation": {"ok": False, "errors": [], "warnings": []},
    }
    if sleeve_only:
        meta["playback"]["weapon_variant"] = (
            "clip_info.<clip>.weapon_variant is null: %s has no hand variants, so nothing swaps. The fist / open hand "
            "poses are the hero's own keyed fingers; clip_info.<clip>.hand_pose lists them per hand for reference" % wkey)
        meta["weapon"]["attach"] = ("weapon scene = identity child of weapon_R (a sleeve weapon: the right forearm lies in "
                                    "its sleeve, the fist on its inner handle); it has no offhand node, the left hand is "
                                    "the hero's own")
    meta_p = os.path.join(out_dir, "%s.meta.json" % KEY)
    rep = V.validate_hero(glb, meta=meta, spec=spec)
    errs = errors + rep["errors"]
    meta["validation"] = {"ok": not errs, "errors": errs, "warnings": rep["warnings"],
                          "tool": "tools/blender/gf_hero/validate_glb.py", "source_fidelity_max_error": fid["max_error"]}
    write_json(meta_p, meta)
    final = V.validate_hero(glb, meta="auto", spec=spec)      # exactly what CI runs on the committed pair
    errs = errors + final["errors"]
    section = {"ok": not errs, "errors": errs, "warnings": final["warnings"],
               "glb": rel(glb), "meta": rel(meta_p), "bytes": os.path.getsize(glb), "sha256": meta["glb_sha256"],
               "source_blend": rel(src), "export_settings": {k: v for k, v in settings.items() if k != "export_copyright"},
               "joined_mesh": {"name": mesh_ob.name, "verts": len(mesh_ob.data.vertices), "tris": joined_tris,
                               "double_sided": not chk["closed"]},
               "blender_checks": chk, "source_fidelity": fid, "validation": final}
    p = update_report(KEY, "hero_export", section)
    for w in final["warnings"]:
        log("warning:", w)
    for e in errs:
        log("ERROR:", e)
    log("hero %s: %s -> %s" % (KEY, "OK" if not errs else "FAILED", rel(p)))
    return not errs


# =====================================================================================================================
# the weapon (a chassis model built by the gf_hero stage-2 chain, e.g. anvil_gauntlets)
# =====================================================================================================================

OFFHAND_DISPLAY_X = -0.65     # grip frame: the left pair sits 0.65 m to the weapon's left in the file (display only)


def export_weapon():
    WA = os.path.join(ROOT, "art", "weapons", WEAPON)
    src = os.path.join(WA, "production", "%s_stage2.blend" % WEAPON)
    open_file(src)
    with open(os.path.join(WA, "status.json"), encoding="utf-8") as f:
        wstatus = json.load(f)
    hero = wstatus.get("designed_on")
    scene = bpy.context.scene
    errors, warnings = [], []
    found = {}
    for o in scene.objects:
        if o.type == "MESH" and "gf_socket" in o and "gf_variant" in o:
            found[(o["gf_variant"], o["gf_socket"][-1])] = o
    log("weapon objects:", {"%s_%s" % k: o.name for k, o in found.items()})
    need = [(v, s) for v in ("fist", "open") for s in ("R", "L")]
    for k in need:
        if k not in found:
            errors.append("no %s variant for the %s hand (gf_variant / gf_socket custom properties)" % k)
    if errors:
        raise SystemExit("; ".join(errors))
    chk = {"objects": {}}
    mats = set()
    for (v, s), o in found.items():
        st = surface_stats(o.data)
        st["socket"], st["variant"] = o["gf_socket"], v
        st["materials"] = [m.name for m in o.data.materials if m]
        mats |= set(st["materials"])
        chk["objects"][o.name] = st
        if st["boundary_edges"] or st["nonmanifold_edges"]:
            warnings.append("%s is open (%d boundary / %d non-manifold edges): exported double-sided" % (o.name, st["boundary_edges"], st["nonmanifold_edges"]))
        if len(st["uv_layers"]) != 1:
            errors.append("%s has UV maps %s" % (o.name, st["uv_layers"]))
        # the object's own transform is only the T-pose display placement; the mesh is authored in the grip frame
        g_expect = o.matrix_world
        st["tpose_placement"] = [list(map(lambda x: round(x, 5), r)) for r in g_expect]
    topo = {k: (len(o.data.vertices), len(o.data.polygons)) for k, o in found.items()}
    for s in ("R", "L"):
        if topo[("fist", s)] != topo[("open", s)]:
            warnings.append("the %s fist and open variants differ in topology %s / %s" % (s, topo[("fist", s)], topo[("open", s)]))
    if len(mats) != 1:
        errors.append("materials %s (one weapon material expected)" % sorted(mats))
    mat = bpy.data.materials.get(sorted(mats)[0])
    imgs = material_images(mat)
    chk["material"] = {"name": mat.name, "images": imgs}
    for k in ("basecolor", "emissive", "normal"):
        if not any(k in i["name"] for i in imgs):
            errors.append("material %s has no %s texture" % (mat.name, k))
    for i in imgs:
        if max(i["px"]) > 1024:
            errors.append("texture %s is %s > 1024 px (the gauntlet_pair tier)" % (i["name"], i["px"]))
    closed = all(st["boundary_edges"] == 0 and st["nonmanifold_edges"] == 0 for st in chk["objects"].values())
    mat.use_backface_culling = closed

    # ---- sockets from the geometry (grip frame, Blender axes) ----
    def fist_front(o):
        co = np.array([v.co[:] for v in o.data.vertices])
        ymax = co[:, 1].max()
        front = co[co[:, 1] > ymax - 0.02]
        return Vector((float(front[:, 0].mean()), float(ymax), float(front[:, 2].mean())))

    def lava_centre(o):
        me = o.data
        z = me.attributes.get("gf_zone")
        if z is None:
            return None
        zones = np.empty(len(me.polygons), dtype=np.int32)
        z.data.foreach_get("value", zones)
        cen = np.empty(len(me.polygons) * 3)
        me.polygons.foreach_get("center", cen)
        area = np.empty(len(me.polygons))
        me.polygons.foreach_get("area", area)
        sel = zones == 5                      # s2_geom.ZONES: "lava"
        if not sel.any():
            return None
        c = (cen.reshape(-1, 3)[sel] * area[sel, None]).sum(0) / area[sel].sum()
        return Vector(c.tolist())

    muzzle_R = fist_front(found[("fist", "R")])
    muzzle_L = fist_front(found[("fist", "L")])
    glow = lava_centre(found[("fist", "R")])
    chk["sockets_blender"] = {"muzzle_R": list(muzzle_R), "muzzle_L": list(muzzle_L), "glow_core": list(glow) if glow else None}

    # ---- the export tree ----
    col = bpy.data.collections.new("EXPORT_%s" % WEAPON)
    scene.collection.children.link(col)
    made = []

    def empty(name, parent, loc=(0.0, 0.0, 0.0)):
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "ARROWS"
        e.empty_display_size = 0.05
        col.objects.link(e)
        if parent is not None:
            e.parent = parent
            e.matrix_parent_inverse = Matrix.Identity(4)
        e.matrix_basis = Matrix.Translation(Vector(loc))
        made.append(e)
        return e

    def mesh_node(name, src_ob, parent):
        me = src_ob.data.copy()
        me.name = name
        for ca in list(me.color_attributes):
            me.color_attributes.remove(ca)
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        ob.parent = parent
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.matrix_basis = Matrix.Identity(4)
        made.append(ob)
        return ob

    root = empty(WEAPON, None)
    fist_R = mesh_node("%s_fist_R" % WEAPON, found[("fist", "R")], root)
    open_R = mesh_node("%s_open_R" % WEAPON, found[("open", "R")], root)
    empty("grip_R", root)
    empty("muzzle", root, muzzle_R)
    if glow is not None:
        empty("glow_core", root, glow)
    empty("grip_L", root, (OFFHAND_DISPLAY_X, 0.0, 0.0))
    off = empty("offhand", root, (OFFHAND_DISPLAY_X, 0.0, 0.0))
    fist_L = mesh_node("%s_fist_L" % WEAPON, found[("fist", "L")], off)
    open_L = mesh_node("%s_open_L" % WEAPON, found[("open", "L")], off)
    empty("muzzle_2", off, muzzle_L)
    bpy.context.view_layer.update()
    out_dir = os.path.join(ROOT, "assets", "models", "weapons")
    os.makedirs(out_dir, exist_ok=True)
    glb = os.path.join(out_dir, "%s.glb" % WEAPON)
    select(made, root)
    settings = dict(EXPORT_COMMON, export_skins=False, export_animations=False,
                    export_copyright="GODFORGE. Weapon %s (art/weapons/%s)." % (WEAPON, WEAPON))
    bpy.ops.export_scene.gltf(filepath=glb, **settings)
    log("wrote %s (%.2f MB)" % (rel(glb), os.path.getsize(glb) / 1e6))

    # ---- read back ----
    g = V.Glb(glb)
    doc, names = g.doc, g.names
    wm = V.world_matrices(g)
    tris_mesh = {}
    for i, n in enumerate(g.nodes):
        if "mesh" in n:
            t = 0
            for p in doc["meshes"][n["mesh"]]["primitives"]:
                t += (doc["accessors"][p["indices"]]["count"] if "indices" in p else doc["accessors"][p["attributes"]["POSITION"]]["count"]) // 3
                at = p["attributes"]
                for need in ("POSITION", "NORMAL", "TANGENT", "TEXCOORD_0"):
                    if need not in at:
                        errors.append("%s: no %s" % (names[i], need))
                cols = [k for k in at if k.startswith("COLOR_")]
                if cols:
                    errors.append("%s: vertex colours %s" % (names[i], cols))
            tris_mesh[names[i]] = t
    shown = tris_mesh.get("%s_fist_R" % WEAPON, 0) + tris_mesh.get("%s_fist_L" % WEAPON, 0)
    if shown > 8000:
        errors.append("the pair shows %d triangles > 8000 (gauntlet_pair tier)" % shown)
    roots = [names[i] for i in doc["scenes"][doc.get("scene", 0)]["nodes"]]
    if roots != [WEAPON]:
        errors.append("scene roots %s, expected [%s]" % (roots, WEAPON))
    socks = {}
    for s in ("grip_R", "grip_L", "muzzle", "glow_core", "offhand", "muzzle_2"):
        if s not in names:
            if s in ("grip_R", "grip_L", "muzzle", "offhand", "muzzle_2"):
                errors.append("socket %s missing" % s)
            continue
        m = wm[names.index(s)]
        socks[s] = {"translation": [round(m[r][3], 4) for r in range(3)], "forward": [round(-m[r][2], 4) for r in range(3)],
                    "up": [round(m[r][1], 4) for r in range(3)],
                    "parent": names[g.parent[names.index(s)]] if names.index(s) in g.parent else None}
    if "grip_R" in socks and max(abs(v) for v in socks["grip_R"]["translation"]) > 1e-5:
        errors.append("grip_R is not at the origin")
    if "muzzle" in socks and (socks["muzzle"]["translation"][2] > -0.05 or socks["muzzle"]["forward"][2] > -0.7):
        errors.append("muzzle %s does not sit in front along glTF -Z" % socks["muzzle"])
    if "offhand" in socks and "grip_L" in socks and socks["offhand"]["translation"] != socks["grip_L"]["translation"]:
        errors.append("offhand's origin is not on grip_L")
    for nm in ("%s_fist_L" % WEAPON, "%s_open_L" % WEAPON, "muzzle_2"):
        if nm in names and names[g.parent[names.index(nm)]] != "offhand":
            errors.append("%s is not under offhand" % nm)
    texs = []
    for i, im in enumerate(doc.get("images", [])):
        w, h, fmt = V.image_info(g.image_blob(im))
        texs.append({"name": im.get("name"), "px": [w, h], "format": fmt, "bytes": len(g.image_blob(im))})
        if fmt != "png" or max(w, h) > 1024:
            errors.append("image %s is %s %dx%d (PNG <= 1024 px)" % (im.get("name"), fmt, w, h))
    m0 = doc["materials"][0] if doc.get("materials") else {}
    roles = {"basecolor": m0.get("pbrMetallicRoughness", {}).get("baseColorTexture"), "emissive": m0.get("emissiveTexture"),
             "normal": m0.get("normalTexture")}
    for t in texs:
        idx = [k for k, ref in roles.items() if ref is not None and doc["textures"][ref["index"]]["source"] == texs.index(t)]
        t["role"] = {"basecolor": "base_color", "emissive": "emissive", "normal": "normal"}.get(idx[0]) if idx else "unused"
    if any(v is None for v in roles.values()):
        errors.append("material lacks %s" % [k for k, v in roles.items() if v is None])
    if set(doc.get("extensionsRequired", [])) - V.BEVY_OK or (set(doc.get("extensionsUsed", [])) & V.BANNED):
        errors.append("unsupported / banned extensions %s" % doc.get("extensionsUsed"))
    lo, hi = [1e9] * 3, [-1e9] * 3
    for i, n in enumerate(g.nodes):
        if "mesh" in n:
            for p in doc["meshes"][n["mesh"]]["primitives"]:
                acc = doc["accessors"][p["attributes"]["POSITION"]]
                for x in (acc["min"][0], acc["max"][0]):
                    for y in (acc["min"][1], acc["max"][1]):
                        for z in (acc["min"][2], acc["max"][2]):
                            q = V.apply(wm[i], (x, y, z))
                            lo = [min(lo[k], q[k]) for k in range(3)]
                            hi = [max(hi[k], q[k]) for k in range(3)]
    # the armory's validator (read only): report what it says about this file
    gfa = None
    try:
        gfa_dir = os.path.join(ROOT, "tools", "blender", "gf_assets")
        if gfa_dir not in sys.path:
            sys.path.insert(0, gfa_dir)
        import gfa_validate  # noqa: E402
        gfa = gfa_validate.validate(glb, kind="weapon", tier="gauntlet_pair", key=WEAPON)
        gfa = {"ok": gfa["ok"], "errors": gfa["errors"], "warnings": gfa["warnings"], "tris": gfa.get("tris")}
    except Exception as ex:  # noqa: BLE001 - informational only
        gfa = {"ok": None, "errors": ["could not run gfa_validate: %s" % ex], "warnings": []}
    if gfa.get("errors"):
        warnings.append("gfa_validate (tools/blender/gf_assets, read only): %s" % gfa["errors"])
    # attach to the hero it was designed on (if that hero's GLB is there)
    hero_glb = os.path.join(ROOT, "assets", "models", "characters", "%s.glb" % hero) if hero else None
    attach = None
    if hero_glb and os.path.isfile(hero_glb):
        E2, W2 = [], []
        attach = V.attach_check(V.Glb(hero_glb), glb, E2, W2)
        attach["ok"] = not E2
        errors += E2
    variants = {"default": "fist",
                "fist": {"R": "%s_fist_R" % WEAPON, "L": "%s_fist_L" % WEAPON},
                "open": {"R": "%s_open_R" % WEAPON, "L": "%s_open_L" % WEAPON},
                "note": "all four meshes are visible when the scene spawns: hide the open pair by node name (Visibility::Hidden) "
                        "and swap per hand at the frames the hero sidecar gives (clip_info.<clip>.weapon_variant). The two "
                        "variants of a hand share topology, UVs and the texture."}
    meta = {
        "kind": "weapon", "key": WEAPON, "tier": "gauntlet_pair",
        "tris": shown, "tris_budget": [4000, 8000], "tris_all_variants": sum(tris_mesh.values()), "tris_per_mesh": tris_mesh,
        "textures": texs, "sockets": socks, "variants": variants, "clips": [], "skeleton": None,
        "status": "ai_final_pending_user_approval",
        "axes": "glTF +Y up, 1 unit = 1 m. Grip frame: origin = the right palm centre, -Z = along the fingers (the strike "
                "direction), +Y = out of the back of the hand, +X = right. The scene attaches as an identity child of the "
                "hero's weapon_R; offhand (the left pair, its origin = grip_L = the left palm centre) is re-parented to "
                "weapon_L with an identity transform. offhand's own offset (%.2f m) is a display layout only." % OFFHAND_DISPLAY_X,
        "attach": {"root": "weapon_R", "offhand": "weapon_L", "sleeve_weapon": True,
                   "rules": "a sleeve weapon: the wrist stays straight (bend 0, twist free); the elbow cuff presses into the "
                            "biceps past about 40 deg of elbow flexion (docs/art/GF_HERO_SKELETON.md section 7)"},
        "designed_on": hero,
        "bounds_m": {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]},
        "size_m": round(max(hi[k] - lo[k] for k in range(3)), 3),
        "glb": rel(glb), "glb_bytes": os.path.getsize(glb), "glb_sha256": sha256(glb),
        "source_blend": rel(src), "build_script": "tools/blender/gf_hero/export_glb.py (mesh: tools/blender/gf_hero/s2_weapon.py + s2_gauntlet.py)",
        "toolkit": "tools/blender/gf_hero", "generator": "Blender %s" % bpy.app.version_string, "built": TODAY,
        "validation": {"ok": not errors, "errors": errors, "warnings": warnings, "tool": "tools/blender/gf_hero/export_glb.py",
                       "gfa_validate": gfa},
        "chassis": {"damage_type": "Kinetic", "style": "Fist", "tags": ["melee"]},
    }
    write_json(os.path.join(out_dir, "%s.meta.json" % WEAPON), meta)
    section = {"ok": not errors, "errors": errors, "warnings": warnings, "glb": rel(glb), "meta": "assets/models/weapons/%s.meta.json" % WEAPON,
               "bytes": os.path.getsize(glb), "tris_shown_pair": shown, "tris_per_mesh": tris_mesh, "sockets": socks,
               "textures": texs, "blender_checks": chk, "attach_on_%s" % hero: attach, "gfa_validate": gfa,
               "export_settings": {k: v for k, v in settings.items() if k != "export_copyright"}}
    if hero:
        update_report(hero, "weapons", section, sub=WEAPON)
    for w in warnings:
        log("warning:", w)
    for e in errors:
        log("ERROR:", e)
    log("weapon %s: %s" % (WEAPON, "OK" if not errors else "FAILED"))
    return not errors


ok = export_weapon() if WEAPON else export_hero()
if not ok:
    raise SystemExit(1)
