"""Stage 2, Selene: put the sculpt reference's BODY on the origin (headless Blender).

The shared s2_prepare_blockout.py centres the blockout's bounding box. Selene's capes, hip panels and the stage-1 hair
tail trail behind her and her ragged cloth reaches further on one side, so the box centre is not her body: the body's
centre line (legs, waist, head and the arm axis, measured on horizontal and sagittal sections of the s303 blockout)
sits at x +0.034, and the torso about 0.15 m in front of the box centre. This moves REF_blockout and the concept image
by the given offset, so the symmetric production body stands on the origin (the rig's root) and faces -Y like every
hero. (Same job as Kael's recentre step; a Selene copy so the two tracks never share an uncommitted file.)

  blender -b -P tools/blender/gf_hero/s2_selene_recentre.py -- <retopo_start.blend> --offset -0.034,0.15,0 [--report <json>]
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
set_co(ref.data, get_co(ref.data) + OFF)
emp = bpy.data.objects.get("REF_concept_front")
if emp is not None:
    emp.location = tuple(np.array(emp.location) + np.array([OFF[0], 0.0, OFF[2]]))
co = get_co(ref.data)
lo, hi = co.min(0), co.max(0)
log("REF_blockout moved by", OFF.tolist(), "bounds", lo.round(3).tolist(), hi.round(3).tolist())
bpy.ops.wm.save_as_mainfile(filepath=SRC, compress=True)
if REPORT:
    rep = read_json(REPORT) if os.path.isfile(REPORT) else {}
    rep["recentre"] = {"offset_m": OFF.tolist(), "why": "body centre line on the origin (s2_selene_recentre.py)",
                       "bounds_m": {"min": lo.round(4).tolist(), "max": hi.round(4).tolist()}}
    write_json(REPORT, rep)
