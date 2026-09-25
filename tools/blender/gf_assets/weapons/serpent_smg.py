"""Serpent SMG launcher (toolkit convention: weapons/<key>.py). The build script lives with its art pack,
art/weapons/serpent_smg/source/serpent_smg_build.py; this file only runs it, arguments included.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 ^
      -P tools/blender/gf_assets/weapons/serpent_smg.py -- [--size 1024] [--no-review] [--quick]
"""
import os
import runpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
runpy.run_path(os.path.join(ROOT, "art", "weapons", "serpent_smg", "source", "serpent_smg_build.py"),
               run_name="__main__")
