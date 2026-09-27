"""Stage 2, Kael: put the sculpt reference's BODY on the origin (headless Blender).

The shared s2_prepare_blockout.py centres the blockout's bounding box. Kael's duster trails 0.7 m behind his heels and
his ghost arm reaches 4 cm further than his gun arm, so the box centre is not his body: the body's centre line (legs,
torso, head, arm axis, measured on horizontal sections of the s202 blockout) sits at x -0.03, y -0.225. This moves
REF_blockout and the concept image by the given offset, so the symmetric production body stands on the origin (the
rig's root) and faces -Y like every hero.

  blender -b -P tools/blender/gf_hero/s2_kael_recentre.py -- <retopo_start.blend> --offset 0.03,0.225,0 [--report <json>]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402

from s2lib import get_co, log, opt, read_json, script_args, set_co, write_json  # noqa: E402

argv = script_args(__doc__)
SRC = os.path.abspath(argv[0])
OFF = np.array([float(v) for v in opt(argv, "--offset", "0,0,0", str).split(",")])
REPORT = opt(argv, "--report", None, str)
bpy.ops.wm.open_mainfile(filepath=SRC)
ref = bpy.data.objects["REF_blockout"]
co = get_co(ref.data)
set_co(ref.data, co + OFF)
emp = bpy.data.objects.get("REF_concept_front")
if emp is not None:
    emp.location = tuple(np.array(emp.location) + np.array([OFF[0], 0.0, OFF[2]]))
co = get_co(ref.data)
lo, hi = co.min(0), co.max(0)
log("REF_blockout moved by", OFF.tolist(), "bounds", lo.round(3).tolist(), hi.round(3).tolist())
bpy.ops.wm.save_as_mainfile(filepath=SRC, compress=True)
if REPORT:
    rep = read_json(REPORT) if os.path.isfile(REPORT) else {}
    rep["recentre"] = {"offset_m": OFF.tolist(), "why": "body centre line on the origin (s2_kael_recentre.py)",
                       "bounds_m": {"min": lo.round(4).tolist(), "max": hi.round(4).tolist()}}
    write_json(REPORT, rep)
