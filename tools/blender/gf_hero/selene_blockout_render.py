"""Run a stage-1 blockout renderer with Cycles on the CPU instead of EEVEE (Selene's stage 1).

  blender -b -P tools/blender/gf_hero/selene_blockout_render.py -- <renderer.py> <renderer args...>

  <renderer.py>  tools/blender/gf_hero/render_blockout.py or tools/comfy/render_blockout_parts.py (shared, unchanged)

The shared renderers light their textured views with EEVEE. The GPU is shared (one TRELLIS.2 job at a
time plus another agent), and GODFORGE review renders run on Cycles CPU or Workbench, never EEVEE. This
wrapper reads the renderer's source, swaps its one EEVEE line for a low-sample Cycles CPU setup (same lights,
world, camera and colour management, denoised), and executes it with the renderer's own argv and __file__.
The shared scripts are not edited; the Workbench clay / albedo / silhouette passes are untouched.
"""
import os
import sys

EEVEE = 'scene.render.engine = "BLENDER_EEVEE"'
CYCLES = ('scene.render.engine = "CYCLES"; scene.cycles.device = "CPU"; scene.cycles.samples = %d; '
          'scene.cycles.use_denoising = True; scene.cycles.max_bounces = 4; scene.render.threads_mode = "AUTO"')
SAMPLES = int(os.environ.get("GF_REVIEW_SAMPLES", "24"))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    raise SystemExit(__doc__)
script = os.path.abspath(argv[0])
src = open(script, encoding="utf-8").read()
if src.count(EEVEE) != 1:
    raise SystemExit("expected exactly one EEVEE engine line in %s, found %d" % (script, src.count(EEVEE)))
src = src.replace(EEVEE, CYCLES % SAMPLES)
sys.argv = [sys.argv[0], "--"] + argv[1:]
print("[selene] %s with Cycles CPU, %d samples, denoised (EEVEE swapped out)" % (os.path.basename(script), SAMPLES))
exec(compile(src, script, "exec"), {"__name__": "__main__", "__file__": script})
