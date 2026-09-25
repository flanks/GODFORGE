"""Thundercoil Launcher: shim so every weapon build is reachable as tools/blender/gf_assets/weapons/<key>.py.

The build script lives with its art pack:
    art/weapons/thundercoil_launcher/source/thundercoil_launcher_build.py

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/weapons/thundercoil_launcher.py -- [--size 1024] [--no-review]
"""
import os
import runpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
runpy.run_path(os.path.join(ROOT, "art", "weapons", "thundercoil_launcher", "source", "thundercoil_launcher_build.py"),
               run_name="__main__")
