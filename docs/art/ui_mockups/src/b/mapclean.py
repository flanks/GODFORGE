from PIL import Image, ImageFilter
import numpy as np


def clean_map(im):
    """Remove the preview's text labels (and their dark halos) so the crop can stand in for a minimap."""
    im = im.convert('RGB')
    a = np.asarray(im).astype(np.float32) / 255
    lum = a @ np.array([.3, .59, .11])
    mx = a.max(-1); mn = a.min(-1); sat = (mx - mn) / (mx + 1e-3)
    txt = ((lum > 0.74) | ((sat > 0.5) & (lum > 0.5))).astype(np.uint8) * 255
    near = np.asarray(Image.fromarray(txt).filter(ImageFilter.MaxFilter(11))) > 0
    dark = (lum < 0.14) & near
    mask = Image.fromarray(((txt > 0) | dark).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3))
    out = im
    for k in (9, 15):
        fill = out.filter(ImageFilter.MedianFilter(k))
        out = Image.composite(fill, out, mask)
    return out.filter(ImageFilter.MedianFilter(3))
