"""Colossus Cannon: alias for the real build script, which lives with its art pack in
art/weapons/colossus_cannon/source/colossus_cannon_build.py (the task asked for <key>_build.py next to the
.blend). Running either file rebuilds everything:

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/weapons/colossus_cannon.py -- [--size 1024] [--no-review]
"""
import os
import runpy

BUILD = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
                                     "art", "weapons", "colossus_cannon", "source", "colossus_cannon_build.py"))

if __name__ == "__main__":
    runpy.run_path(BUILD, run_name="__main__")
