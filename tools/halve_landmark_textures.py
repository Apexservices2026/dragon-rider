"""Halve the landmark textures that don't need 2048 px (to keep Git LFS lean).

Run with Blender's bundled Python (it ships OpenImageIO), before tools/import_landmarks.py:
  "C:/Program Files/Blender Foundation/Blender 5.0/5.0/python/bin/python.exe" -I tools/halve_landmark_textures.py
Writes 1024 px copies to Saved/Generated/World/half/ (Vertex's originals stay untouched); import_landmarks.py uses a
copy from there when one exists. Normal maps are renormalised after the box filter.
"""
import os
import sys

import numpy as np
import OpenImageIO as oiio

SRC = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Game', 'DragonRider', 'Saved', 'Generated', 'World'))
OUT = os.path.join(SRC, 'half')
# Runes keep their 2048 colour and glow maps (the carved letters need them); shingle roofs are seen from afar.
HALVE = ['T_Runes_N_DX.png', 'T_Runes_R.png', 'T_Shingle_BC.png', 'T_Shingle_N_DX.png', 'T_Shingle_R.png']

os.makedirs(OUT, exist_ok=True)
for name in HALVE:
    src = os.path.join(SRC, name)
    inp = oiio.ImageInput.open(src)
    if not inp:
        sys.exit('cannot open ' + src)
    spec = inp.spec()
    px = inp.read_image(0, 0, 0, spec.nchannels, oiio.FLOAT)
    inp.close()
    a = np.asarray(px, dtype=np.float32).reshape(spec.height, spec.width, spec.nchannels)
    h = a.reshape(spec.height // 2, 2, spec.width // 2, 2, spec.nchannels).mean(axis=(1, 3))
    if '_N' in name:
        v = h[..., :3] * 2.0 - 1.0
        v /= np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-6)
        h[..., :3] = v * 0.5 + 0.5
    out_spec = oiio.ImageSpec(spec.width // 2, spec.height // 2, spec.nchannels, oiio.UINT8)
    o = oiio.ImageOutput.create(os.path.join(OUT, name))
    o.open(os.path.join(OUT, name), out_spec)
    o.write_image(np.clip(np.round(h * 255.0), 0, 255).astype(np.uint8))
    o.close()
    print('%s: %d -> %d px, %d -> %d KB' % (name, spec.width, spec.width // 2, os.path.getsize(src) // 1024,
                                            os.path.getsize(os.path.join(OUT, name)) // 1024))
