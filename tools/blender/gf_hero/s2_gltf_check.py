"""Check that a stage-2 production .blend carries into glTF the way Bevy 0.20 will load it (not the stage-5
export: this writes a scratch GLB to verify the material wiring).

  blender -b <production.blend> -P tools/blender/gf_hero/s2_gltf_check.py -- <scratch.glb> <report.json>

Exports every mesh object with Blender's glTF exporter (binary, tangents on, no Draco / meshopt /
quantisation) and reads the result back: each material must have a baseColorTexture, an emissiveTexture and
a normalTexture (bevy_gltf 0.20 maps them to StandardMaterial base_color_texture / emissive_texture /
normal_map_texture), each primitive must carry NORMAL, TANGENT and TEXCOORD_0 (MikkTSpace tangents, the
space the normal map was baked in), and nothing may be in extensionsRequired that bevy_gltf cannot load.
"""
import json
import os
import struct
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, REPORT = (os.path.abspath(a) for a in argv[:2])
os.makedirs(os.path.dirname(GLB), exist_ok=True)
for o in bpy.data.objects:
    o.select_set(o.type == "MESH")
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True, export_tangents=True,
                          export_normals=True, export_texcoords=True, export_materials="EXPORT",
                          export_draco_mesh_compression_enable=False, export_apply=False, export_yup=True)
with open(GLB, "rb") as f:
    head = f.read(20)
    clen, _ = struct.unpack("<II", head[12:20])
    doc = json.loads(f.read(clen).decode("utf-8"))
res = {"glb": os.path.basename(GLB), "bytes": os.path.getsize(GLB), "materials": [], "primitives": 0,
       "missing_tangents": 0, "extensionsRequired": doc.get("extensionsRequired", []), "images": len(doc.get("images", []))}
ok = True
for m in doc.get("materials", []):
    pbr = m.get("pbrMetallicRoughness", {})
    e = {"name": m.get("name"), "baseColorTexture": "baseColorTexture" in pbr, "emissiveTexture": "emissiveTexture" in m,
         "normalTexture": "normalTexture" in m, "emissiveStrength": m.get("extensions", {}).get("KHR_materials_emissive_strength", {}).get("emissiveStrength")}
    ok &= e["baseColorTexture"] and e["emissiveTexture"] and e["normalTexture"]
    res["materials"].append(e)
for me in doc.get("meshes", []):
    for p in me["primitives"]:
        res["primitives"] += 1
        a = p["attributes"]
        if not all(k in a for k in ("NORMAL", "TANGENT", "TEXCOORD_0")):
            res["missing_tangents"] += 1
            ok = False
res["ok"] = bool(ok and not res["extensionsRequired"])
with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(res, f, indent=1)
    f.write("\n")
print("[gltf_check]", res)
if not res["ok"]:
    raise SystemExit("glTF check failed")
