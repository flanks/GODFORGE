"""Regenerate every GODFORGE VFX asset, the manifest and the contact sheets.

    python tools/vfx/build_all.py                 # everything (about 2-3 minutes on 32 threads)
    python tools/vfx/build_all.py --skip-blender  # textures, manifest and sheets only
    python tools/vfx/build_all.py --only impacts,bursts --no-sheets

Python 3 with Pillow, numpy and scipy (the ComfyUI standalone env has them); Blender 5.2 for the meshes
(BLENDER env var or the default install path). Output:

    assets/vfx/atlas/*.png  trails/  smears/  noise/  ramps/  meshes/*.glb  vfx_assets.json
    docs/art/vfx_concepts/assets_*.png

Everything is deterministic (fixed seeds). The format is documented in vfxlib.py and in the manifest's
"conventions" block; the art direction is docs/art/VFX_STYLE.md.
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import vfxlib as L  # noqa: E402

BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
STAGES = ["impacts", "particles", "elements", "bursts", "glyphs", "strips", "bodies", "noise"]


def glb_stats(path):
    with open(path, "rb") as f:
        b = f.read()
    n = struct.unpack("<I", b[12:16])[0]
    js = json.loads(b[20:20 + n])
    tris = 0
    lo, hi = [1e9] * 3, [-1e9] * 3
    attrs = set()
    for m in js["meshes"]:
        for p in m["primitives"]:
            attrs |= set(p["attributes"].keys())
            a = js["accessors"][p["indices"]] if "indices" in p else js["accessors"][p["attributes"]["POSITION"]]
            tris += a["count"] // 3
            pa = js["accessors"][p["attributes"]["POSITION"]]
            lo = [min(x, y) for x, y in zip(lo, pa["min"])]
            hi = [max(x, y) for x, y in zip(hi, pa["max"])]
    return tris, [round(v, 3) for v in lo], [round(v, 3) for v in hi], sorted(attrs)


def register_meshes():
    import blender_meshes as BM
    out = {}
    for name, meta in BM.MESHES.items():
        rel = f"meshes/{name}.glb"
        path = os.path.join(L.OUT, rel)
        if not os.path.exists(path):
            continue
        tris, lo, hi, attrs = glb_stats(path)
        out[name] = tris
        e = dict(file=rel, kind="mesh", frames=1, fps=None, grid=None, intended=meta["intended"], group=meta["group"],
                 tris=tris, bounds_min=lo, bounds_max=hi, attributes=attrs, uv=meta["uv"], pivot=meta["pivot"],
                 orient=meta["orient"])
        L.register(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-blender", action="store_true")
    ap.add_argument("--no-sheets", action="store_true")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    L.load_manifest()
    t0 = time.time()
    import atlas_bodies
    import atlas_bursts
    import atlas_elements
    import atlas_glyphs
    import atlas_impacts
    import atlas_particles
    import atlas_strips
    import make_noise
    mods = {"impacts": atlas_impacts, "particles": atlas_particles, "elements": atlas_elements, "bursts": atlas_bursts,
            "glyphs": atlas_glyphs, "strips": atlas_strips, "bodies": atlas_bodies, "noise": make_noise}
    for st in STAGES:
        if only and st not in only:
            continue
        t = time.time()
        mods[st].build()
        print(f"[{st}] {time.time() - t:.1f}s")
        L.write_manifest()
    scratch = os.path.join(L.ROOT, "target", "vfx_preview")
    os.makedirs(scratch, exist_ok=True)
    render = os.path.join(scratch, "meshes_render.png")
    if not args.skip_blender and (not only or "meshes" in only):
        t = time.time()
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "blender_meshes.py"), "--",
                            "--preview", render], capture_output=True, text=True)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("VFX")]
        print("\n".join(lines[-3:]))
        if r.returncode != 0 or not any(ln.startswith("VFXPREVIEW") for ln in lines):
            print(r.stdout[-3000:], r.stderr[-3000:])
            raise SystemExit("blender_meshes.py failed")
        print(f"[meshes] {time.time() - t:.1f}s")
    import sheets
    sheets.BM_TRIS.update(register_meshes())
    path = L.write_manifest()
    print("manifest", os.path.relpath(path, L.ROOT), len(L.MANIFEST), "assets")
    if not args.no_sheets:
        sheets.build(render if os.path.exists(render) else None)
    # size gate: every shipped file < 2 MB
    total = 0
    for dp, _, fs in os.walk(L.OUT):
        for f in fs:
            s = os.path.getsize(os.path.join(dp, f))
            total += s
            if s >= 2 * 1024 * 1024:
                raise SystemExit(f"{f} is {s / 1e6:.2f} MB (limit 2 MB)")
    print(f"assets/vfx total {total / 1e6:.2f} MB · done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
