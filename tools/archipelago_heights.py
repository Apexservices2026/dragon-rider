"""Ground heights of the archipelago for the Unreal placement scripts (pure Python, no numpy).

Line traces return nothing inside a commandlet, so placement samples the islands' heightmaps
(Saved/Generated/Archipelago/*.r16, the data the landscapes were imported from). All values in Unreal cm.
"""
import array
import json
import math
import os


class Heightmap:
    def __init__(self, gen_dir, isl):
        self.n = isl['size_px']
        self.step = isl['m_per_px'] * 100.0
        self.x0, self.y0 = isl['landscape_location_cm'][0], isl['landscape_location_cm'][1]
        self.x1, self.y1 = self.x0 + self.step * (self.n - 1), self.y0 + self.step * (self.n - 1)
        self.zs = isl['z_scale'] / 128.0
        self.v = array.array('H')
        with open(os.path.join(gen_dir, isl['heightmap']), 'rb') as f:
            self.v.fromfile(f, self.n * self.n)

    def get(self, x, y):
        if x < self.x0 or y < self.y0 or x >= self.x1 or y >= self.y1:
            return None
        fx, fy = (x - self.x0) / self.step, (y - self.y0) / self.step
        i, j = int(fx), int(fy)
        u, w = fx - i, fy - j
        k = j * self.n + i
        V, n = self.v, self.n
        h = (V[k] * (1 - u) + V[k + 1] * u) * (1 - w) + (V[k + n] * (1 - u) + V[k + n + 1] * u) * w
        return (h - 32768.0) * self.zs


class Archipelago:
    OPEN_SEA = -6000.0

    def __init__(self, gen_dir):
        self.layout = json.load(open(os.path.join(gen_dir, 'archipelago.json')))
        self.maps = [Heightmap(gen_dir, isl) for isl in self.layout['islands'].values()]

    def height(self, x, y):
        best = None
        for m in self.maps:
            h = m.get(x, y)
            if h is not None and (best is None or h > best):
                best = h
        return self.OPEN_SEA if best is None else best

    def footprint(self, x, y, yaw, hx, hy, n=3):
        """Heights under an hx x hy (half extents, cm) rectangle rotated by yaw (deg), n x n samples."""
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        out = []
        for a in range(n):
            for b in range(n):
                lx = -hx + 2 * hx * a / (n - 1)
                ly = -hy + 2 * hy * b / (n - 1)
                out.append(self.height(x + lx * c - ly * s, y + lx * s + ly * c))
        return out
