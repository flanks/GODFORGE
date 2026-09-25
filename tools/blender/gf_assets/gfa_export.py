"""gf_assets export: glTF binary (+Y up, uncompressed) + sidecar <key>.meta.json + validation.

  from gfa_export import export_asset
  rep = export_asset("weapon", "sunspike_shotgun", "two_handed", root=weapon_root_empty,
                     source_blend=..., build_script=__file__)        # exits 1 when validation fails

Stand-alone re-validation (no Blender):  python tools/blender/gf_assets/gfa_validate.py <glb>

What gets exported: `root` and everything parented under it (mesh, socket empties, armature), nothing
else in the scene (review mannequins, cameras and lights never leak into the GLB). Modifiers are
applied, images are embedded as PNG, no Draco / meshopt (bevy_gltf 0.20 cannot load them,
docs/ART_PIPELINE.md section 6). Rigged assets export every NLA track as one animation named after
the track ({key}_{clip}[@loop], gfa_rig.push_clip).

Adapted from Ashen Covenant tools/blender/ac_humanoid_enemy/e06_export_glb.py (NLA-track export,
post-export GLB inspection) and GODFORGE tools/comfy/check_art.py (extension gate).
"""
import hashlib
import os
import sys
import time

import bpy

import gfa_common as C
import gfa_spec as SPEC
import gfa_validate as V


def _descendants(obj):
    out = [obj]
    for c in obj.children:
        out.extend(_descendants(c))
    return out


def prepare(root, kind):
    """Pre-export hygiene. Weapons: the root IS the grip frame, so it must sit at the world origin with no
    rotation / scale. Mesh objects that are not skinned get their object transform baked into the mesh data
    (relative to their parent), so the GLB carries clean identity mesh nodes. Returns a list of fixes."""
    from mathutils import Matrix
    fixes = []
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    if kind == "weapon" and not _is_identity(root.matrix_world):
        root.matrix_world = Matrix.Identity(4)
        fixes.append("weapon root %s reset to the identity (grip frame = world origin)" % root.name)
    for o in _descendants(root):
        if o.type != "MESH" or any(m.type == "ARMATURE" for m in o.modifiers):
            continue
        if not _is_identity(o.matrix_basis):
            o.data.transform(o.matrix_basis)
            o.matrix_basis = Matrix.Identity(4)
            fixes.append("baked the object transform of %s into its mesh" % o.name)
    bpy.context.view_layer.update()
    for f in fixes:
        C.log("prepare:", f)
    return fixes


def _is_identity(m, eps=1e-6):
    return all(abs(m[r][c] - (1.0 if r == c else 0.0)) < eps for r in range(4) for c in range(4))


def export_glb(path, objs, animations=False):
    """Export exactly `objs` to a GLB (Y up, applied modifiers, embedded PNGs, no compression)."""
    C.ensure_dir(os.path.dirname(path))
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        o.hide_set(False)
        o.hide_viewport = False
    C.select(objs)
    kw = dict(
        filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=True,
        export_texcoords=True, export_normals=True, export_tangents=False, export_materials="EXPORT",
        export_image_format="AUTO", export_vertex_color="NONE", export_attributes=False,
        export_draco_mesh_compression_enable=False, export_extras=False, export_cameras=False,
        export_lights=False, export_skins=True, export_influence_nb=4, export_all_influences=False,
        export_def_bones=True, export_rest_position_armature=True, export_animations=animations,
        export_morph=False,
    )
    if animations:
        kw.update(export_animation_mode="NLA_TRACKS", export_frame_range=False, export_force_sampling=True,
                  export_optimize_animation_size=True, export_anim_single_armature=True,
                  export_reset_pose_bones=True, export_bake_animation=False)
    props = bpy.ops.export_scene.gltf.get_rna_type().properties
    if "export_meshopt_compression_enable" in props:
        kw["export_meshopt_compression_enable"] = False
    if "export_use_gltfpack" in props:
        kw["export_use_gltfpack"] = False
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})
    return path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_asset(kind, key, tier, root, source_blend=None, build_script=None, out=None, extra=None,
                 fail_hard=True):
    """Export `root` + descendants to assets/models/<kind>s/<key>.glb, validate, write <key>.meta.json.
    Returns the validation report; on failure prints the errors and exits 1 (fail_hard) or returns."""
    out = out or C.model_path(kind, key)
    fixes = prepare(root, kind)
    objs = _descendants(root)
    rigged = any(o.type == "ARMATURE" for o in objs)
    tris_blender = C.count_tris(objs)
    t = time.time()
    export_glb(out, objs, animations=rigged)
    C.log("exported %s (%.2f MB, %.1fs)" % (C.rel(out), os.path.getsize(out) / 1e6, time.time() - t))
    meta = {"kind": kind, "key": key, "tier": tier}
    rep = V.validate(out, kind, tier, key, meta)
    arm = next((o for o in objs if o.type == "ARMATURE"), None)
    meta.update({
        "tris": rep.get("tris"),
        "tris_budget": rep.get("budget"),
        "textures": rep.get("textures"),
        "sockets": rep.get("sockets"),
        "clips": rep.get("clips", []),
        "skeleton": arm.name if arm else None,
        "status": SPEC.STATUS_AI_FINAL,
        "axes": ("glTF +Y up, 1 unit = 1 m. " + (
            "Grip frame: origin = palm centre of the main hand, -Z = barrel/forward, +Y = up, +X = right; "
            "attach as a child of the hand socket / aim pivot with an identity transform."
            if kind == "weapon" else
            "Creature faces glTF +Z (Blender -Y), ground contact at y = 0; the engine turns it with "
            "yaw(angle) * rot_y(PI).")),
        "bounds_m": rep.get("bounds"),
        "size_m": rep.get("length_m", rep.get("height_m")),
        "glb": C.rel(out),
        "glb_bytes": os.path.getsize(out),
        "glb_sha256": sha256(out),
        "source_blend": C.rel(source_blend) if source_blend else None,
        "build_script": C.rel(build_script) if build_script else None,
        "toolkit": "tools/blender/gf_assets (spec v%d)" % SPEC.SPEC_VERSION,
        "generator": "Blender %s" % bpy.app.version_string,
        "built": time.strftime("%Y-%m-%d"),
        "validation": {"ok": rep["ok"], "errors": rep["errors"], "warnings": rep["warnings"]},
    })
    if fixes:
        meta["export_fixes"] = fixes
    if tris_blender != rep.get("tris"):
        meta["tris_note"] = "Blender counts %d tris; the GLB has %d (split normals/UV seams do not add tris)" % (
            tris_blender, rep.get("tris"))
    if extra:
        meta.update(extra)
    mpath = os.path.splitext(out)[0] + ".meta.json"
    C.write_json(mpath, meta)
    for w in rep["warnings"]:
        C.log("warning:", w)
    for e in rep["errors"]:
        C.log("ERROR:", e)
    C.log("validation %s: %s tris (budget %s), textures %s, sockets %s, clips %s" % (
        "OK" if rep["ok"] else "FAILED", rep.get("tris"), rep.get("budget"),
        [t_["px"] for t_ in rep.get("textures", [])], sorted(rep.get("sockets", {})), rep.get("clips", [])))
    if not rep["ok"] and fail_hard:
        sys.stdout.flush()
        sys.exit(1)
    return rep


if __name__ == "__main__":
    # blender -b <file.blend> -P gfa_export.py -- <kind> <key> <tier> <root object name>
    a = C.script_args()
    if len(a) < 4:
        raise SystemExit(__doc__)
    export_asset(a[0], a[1], a[2], bpy.data.objects[a[3]], source_blend=bpy.data.filepath or None)
