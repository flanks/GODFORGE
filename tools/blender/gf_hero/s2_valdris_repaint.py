"""Iteration aid for Valdris's stage-2 paint: repaint the base-colour and emissive atlases from a paint cache,
without the UV and bake steps of s2_texture.py (plain Python with numpy + PIL, e.g. ComfyUI's standalone python).

  GF_VALDRIS_PAINT_CACHE=<cache.npz> blender -b -P s2_texture.py -- ...     # once: writes cache.npz + cache.json
  <python> tools/blender/gf_hero/s2_valdris_repaint.py <cache.npz> <texture.json> <texture_dir>

The cache holds every per-texel map the painter reads (including the edge bake) and the atlas' valid-texel mask;
the paint settings come fresh from <texture.json> (its "paint" block; the eye / mouth keys that s2_texture.py
derives from the fit report are kept from the cache). Writes <texture_dir>/valdris_basecolor.png and
valdris_emissive.png the way s2_texture.py does (sRGB values, gutters dilated). The shipped textures always come from
a full s2_texture.py run; this only shortens the look-development loop.
"""
import json
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_valdris_paint as VP  # noqa: E402


def main(argv):
    cache, texcfg, texdir = argv[:3]
    t0 = time.time()
    z = np.load(cache)
    valid = z["_valid"]
    maps = {k: z[k] for k in z.files if k != "_valid"}
    side = json.load(open(os.path.splitext(cache)[0] + ".json", encoding="utf-8"))
    cfg = json.load(open(texcfg, encoding="utf-8"))
    pc = dict(side["cfg"])
    pc.update(cfg["paint"])
    base, emis = VP.paint(maps, side["zones"], side["pal"], pc)
    size = valid.shape[0]
    margin = cfg["uv"]["margin_px"] + 8
    os.makedirs(texdir, exist_ok=True)
    for arr, name in ((base, cfg["texture_names"]["base_color"]), (emis, cfg["texture_names"]["emissive"])):
        img = np.zeros((size, size, 3), dtype=np.float32)
        img[valid] = arr
        img = VP.dilate(img, valid, margin)
        px = np.round(np.clip(img, 0, 1) * 255).astype(np.uint8)[::-1]      # Blender rows run bottom-up
        Image.fromarray(px, "RGB").save(os.path.join(texdir, name + ".png"))
    print("[repaint] %s in %.0fs" % (texdir, time.time() - t0))


if __name__ == "__main__":
    main(sys.argv[1:])
