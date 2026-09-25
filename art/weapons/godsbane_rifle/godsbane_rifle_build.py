"""Rebuild the Godsbane Rifle art pack (model, paint, .blend, GLB + meta.json, validation, review renders).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P art/weapons/godsbane_rifle/godsbane_rifle_build.py -- [--size 1024] [--no-review]

This is a launcher. The build itself lives in the shared toolkit next to the other weapons, at
tools/blender/gf_assets/weapons/godsbane_rifle.py (see tools/blender/gf_assets/README.md), so every weapon
is regenerated the same way. Arguments after "--" pass straight through.
"""
import os
import runpy

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "..", "..", "tools", "blender", "gf_assets", "weapons",
                                       "godsbane_rifle.py"))
runpy.run_path(SCRIPT, run_name="__main__")
