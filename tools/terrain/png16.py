"""Tiny dependency-free PNG writer/reader for numpy arrays (16-bit grey heightmaps, 8-bit RGB previews)."""
import struct
import zlib

import numpy as np


def _chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path, img):
    """img: (H, W) uint16 / uint8 grey, or (H, W, 3) uint8 RGB."""
    img = np.ascontiguousarray(img)
    if img.ndim == 2 and img.dtype == np.uint16:
        depth, ctype, rows = 16, 0, img.astype('>u2')
    elif img.ndim == 2:
        depth, ctype, rows = 8, 0, img.astype(np.uint8)
    else:
        depth, ctype, rows = 8, 2, img.astype(np.uint8)
    h, w = img.shape[:2]
    raw = rows.reshape(h, -1).view(np.uint8)
    raw = np.concatenate([np.zeros((h, 1), np.uint8), raw], axis=1)  # filter byte 0 per row
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, depth, ctype, 0, 0, 0)))
        f.write(_chunk(b'IDAT', zlib.compress(raw.tobytes(), 6)))
        f.write(_chunk(b'IEND', b''))


def read_png16(path):
    """Read a 16-bit greyscale, non-interlaced PNG written by write_png (filter 0 only)."""
    with open(path, 'rb') as f:
        data = f.read()
    pos, idat, w = 8, b'', 0
    while pos < len(data):
        n, = struct.unpack('>I', data[pos:pos + 4]); tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        if tag == b'IHDR':
            w, h, depth, ctype = struct.unpack('>IIBB', body[:10])
            assert depth == 16 and ctype == 0, 'expected 16-bit grey'
        elif tag == b'IDAT':
            idat += body
        pos += 12 + n
    raw = np.frombuffer(zlib.decompress(idat), np.uint8).reshape(h, 1 + 2 * w)
    assert not raw[:, 0].any(), 'only filter type 0 supported'
    return raw[:, 1:].copy().view('>u2').astype(np.uint16)
