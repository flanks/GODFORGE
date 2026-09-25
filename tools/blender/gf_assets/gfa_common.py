"""gf_assets shared basics for headless Blender 5.2 (bpy): paths, logging, arguments, scene reset,
axes, selection/collection helpers, colour conversion and the art-pack status file.

Adapted from GODFORGE tools/blender/gf_hero/s2lib.py, which itself adapts Ashen Covenant
tools/blender/ac_humanoid_enemy/ac_common.py (log / json / selection / collection / save helpers).

AXES AND UNITS (the mapping every gf_assets script uses; docs/art/WEAPONS.md section 2)
  * 1 Blender unit = 1 m, Z up, feet / ground contact on z = 0.
  * Creatures (heroes, enemies) face Blender -Y; +X is the creature's LEFT. glTF export with +Y up
    maps Blender (x, y, z) -> glTF (x, z, -y), so the creature faces glTF +Z (the glTF "front").
  * Weapons are authored in GRIP space: origin = palm centre of the main (right) hand, +Y = the
    barrel / forward, +Z = up (the weapon's top), +X = the weapon's right. The barrel therefore
    exports to glTF -Z.
  * The engine (crates/gf_client/src/palette.rs yaw()/flat(), scene.rs): sim (x, y) -> Bevy world
    (x, 0, -y); sim +y is world -Z; yaw(angle) = rot_y(angle - PI/2) turns a mesh whose forward is
    world -Z to face the sim angle.
      - weapon scenes: forward is already -Z -> child of the aim pivot / hand socket with an
        identity rotation;
      - creature scenes: forward is +Z -> rotation = yaw(angle) * rot_y(PI) = rot_y(angle + PI/2).
"""
import json
import math
import os
import subprocess
import sys
import time

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import gfa_spec as SPEC  # noqa: E402
import gfa_model as model  # noqa: E402,F401  (modelling helpers, also reachable as gfa_common.model)

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
COMFY_PY = r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe"
_T0 = time.time()


# ---- logging, paths, json, arguments -------------------------------------------------------------

def log(*args):
    print("[gfa %6.1fs]" % (time.time() - _T0), *args, flush=True)


def rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")


def absp(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path.replace("/", os.sep))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def write_json(path, data, quiet=False):
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    if not quiet:
        log("wrote", rel(path))


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path, text):
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def script_args():
    """Arguments after '--' on the Blender command line."""
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def opt(argv, name, default, cast=str):
    """Value after `name` in argv ('--size 1024'), cast; `default` when absent."""
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def flag(argv, name):
    return name in argv


def pack_dir(kind, key):
    """art/<weapons|enemies>/<key>/ (created)."""
    return ensure_dir(os.path.join(ROOT, "art", SPEC.KINDS[kind], key))


def model_path(kind, key):
    return os.path.join(ROOT, "assets", "models", SPEC.KINDS[kind], key + ".glb")


# ---- scene ------------------------------------------------------------------------------------

def reset_scene(fps=30):
    """Empty factory scene: metric, 1 unit = 1 m, CPU Cycles available, `fps` frames per second."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = 1.0
    us.length_unit = "METERS"
    scene.render.fps = fps
    scene.render.fps_base = 1.0
    use_cpu(scene)
    return scene


def use_cpu(scene=None):
    """Cycles on the CPU only (the 8 GB GPU is shared with ComfyUI / TRELLIS / the game)."""
    scene = scene or bpy.context.scene
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "NONE"
    except Exception:  # noqa: BLE001 - add-on missing in some builds; the scene setting still applies
        pass
    scene.cycles.device = "CPU"
    return scene


def select_only(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def select(objs, active=None):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def get_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def move_to_collection(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def link(obj, col=None):
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


def remove_objects(objs):
    for o in list(objs):
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and getattr(data, "users", 1) == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)


def apply_transforms(obj, location=True, rotation=True, scale=True):
    select_only(obj)
    bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)


def save_blend(path, compress=True):
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=compress, copy=False)
    log("saved", rel(path), "(%.2f MB)" % (os.path.getsize(path) / 1e6))


def add_empty(name, location=(0, 0, 0), rotation=None, size=0.05, parent=None, display="ARROWS", col=None):
    """An empty (socket). rotation: Euler degrees (x, y, z) or a 3x3/4x4 Matrix or a Quaternion."""
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = display
    e.empty_display_size = size
    link(e, col)
    if parent is not None:
        e.parent = parent
    m = Matrix.Translation(Vector(location))
    if rotation is not None:
        if isinstance(rotation, (tuple, list)):
            from mathutils import Euler
            r = Euler([math.radians(a) for a in rotation], "XYZ").to_matrix().to_4x4()
        elif hasattr(rotation, "to_matrix"):
            r = rotation.to_matrix().to_4x4()
        else:
            r = Matrix(rotation).to_4x4()
        m = m @ r
    e.matrix_basis = m
    return e


def frame_from_axes(origin, y_axis, z_hint=(0, 0, 1)):
    """4x4 frame with +Y along y_axis and +Z as close to z_hint as possible (right-handed)."""
    y = Vector(y_axis).normalized()
    z = Vector(z_hint)
    z = (z - y * z.dot(y))
    if z.length < 1e-6:
        z = Vector((1, 0, 0)) - y * y.x
    z.normalize()
    x = y.cross(z)
    m = Matrix.Identity(4)
    for r in range(3):
        m[r][0], m[r][1], m[r][2], m[r][3] = x[r], y[r], z[r], origin[r]
    return m


def blender_to_gltf(v):
    """Blender (x, y, z) -> glTF / Bevy (x, z, -y) (export with +Y up)."""
    return (v[0], v[2], -v[1])


def world_bounds(objs):
    """(lo, hi) Vector bounds of evaluated mesh objects in world space."""
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        for v in me.vertices:
            p = mw @ v.co
            lo = Vector((min(lo.x, p.x), min(lo.y, p.y), min(lo.z, p.z)))
            hi = Vector((max(hi.x, p.x), max(hi.y, p.y), max(hi.z, p.z)))
        ev.to_mesh_clear()
    return lo, hi


def count_tris(objs):
    """Triangles after modifiers (what the exporter writes)."""
    dg = bpy.context.evaluated_depsgraph_get()
    n = 0
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        n += len(me.loop_triangles)
        ev.to_mesh_clear()
    return n


# ---- colour -------------------------------------------------------------------------------------

def hex_rgb(h):
    return SPEC.hex_to_rgb01(h)


def s2l(c):
    """sRGB 0..1 -> linear (scalar)."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def l2s(c):
    c = max(0.0, c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_linear(h, alpha=1.0):
    """'#RRGGBB' -> linear RGBA tuple for node sockets / diffuse_color."""
    r, g, b = hex_rgb(h)
    return (s2l(r), s2l(g), s2l(b), alpha)


# ---- art pack bookkeeping ----------------------------------------------------------------------

def write_pack_status(kind, key, outputs, notes, tier=None, extra=None):
    """art/<kind>s/<key>/status.json in the art-pipeline schema (docs/ART_PIPELINE.md section 1,
    tools/comfy/check_art.py rules): the AI build is done, the user's visual approval is pending."""
    today = time.strftime("%Y-%m-%d")
    st = {
        "asset": key,
        "kind": kind,
        "tier": tier,
        "pipeline": "docs/art/%s.md (built with tools/blender/gf_assets)" % ("WEAPONS" if kind == "weapon" else "ENEMIES"),
        "updated": today,
        "status_values": "not_started | in_progress | done | stand_in | pending_human | blocked",
        "final": False,
        "stages": {
            "1_build": {"status": "done", "human_signoff_required": False, "outputs": list(outputs),
                        "notes": notes},
            "2_user_approval": {"status": "pending_human", "human_signoff_required": True, "outputs": [],
                                "notes": "The user gives the final visual approval (meta.json status "
                                         "%s until then)." % SPEC.STATUS_AI_FINAL},
        },
    }
    if extra:
        st.update(extra)
    path = os.path.join(pack_dir(kind, key), "status.json")
    write_json(path, st)
    return path


def run_comfy_python(script, *args, check=True):
    """Run a PIL/numpy helper (gfa_sheet.py) with ComfyUI's standalone python (Blender has no PIL)."""
    cmd = [COMFY_PY, os.path.join(HERE, script)] + [str(a) for a in args]
    log("run", " ".join(os.path.basename(c) if i < 2 else c for i, c in enumerate(cmd)))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip(), flush=True)
    if r.returncode != 0:
        print(r.stderr, flush=True)
        if check:
            raise RuntimeError("%s failed (%d)" % (script, r.returncode))
    return r.returncode
