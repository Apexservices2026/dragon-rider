"""Shared numpy terrain helpers: noise, resampling, distance fields, hydraulic (stream power) and thermal erosion.

Pure numpy + the standard library (no scipy / numba). Grids are float arrays indexed [row, col]; row = +Y, col = +X
in Unreal world space. Cell size `dx` is in metres.

Hydraulic erosion is the stream power law solved implicitly on a D8 drainage network (Braun & Willett 2013),
driven by an uplift field (the island's "intent" shape) until the relief nears steady state. That produces the
dendritic valley networks and sharp ridges of real mountain ranges. The serial parts (drainage area and implicit
solve, both in topological order) run as plain Python loops over lists, roughly 1 s per million cells.
"""
import heapq
import math

import numpy as np

SQ2 = math.sqrt(2.0)
# D8 neighbour offsets (drow, dcol) and their lengths in cells
NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
NB_LEN = [SQ2, 1, SQ2, 1, 1, SQ2, 1, SQ2]


# ---------------------------------------------------------------------------------------------------------- noise
class Perlin:
    """Vectorised 2D gradient noise with a fixed permutation table (deterministic per seed)."""

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        p = rng.permutation(256)
        self.perm = np.concatenate([p, p]).astype(np.int64)
        ang = rng.random(256) * 2 * np.pi
        self.gx, self.gy = np.cos(ang), np.sin(ang)

    def __call__(self, x, y):
        xi, yi = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
        xf, yf = x - xi, y - yi
        xi &= 255; yi &= 255
        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        P = self.perm

        def g(ix, iy, dx_, dy_):
            h = P[P[ix] + iy]
            return self.gx[h] * dx_ + self.gy[h] * dy_
        n00 = g(xi, yi, xf, yf)
        n10 = g(xi + 1, yi, xf - 1, yf)
        n01 = g(xi, yi + 1, xf, yf - 1)
        n11 = g(xi + 1, yi + 1, xf - 1, yf - 1)
        a = n00 + u * (n10 - n00)
        b = n01 + u * (n11 - n01)
        return (a + v * (b - a)) * 1.41  # ~[-1, 1]


def fbm(noise, x, y, octaves=5, lac=2.03, gain=0.5):
    amp, f, out, norm = 1.0, 1.0, 0.0, 0.0
    for o in range(octaves):
        out = out + amp * noise(x * f + o * 17.3, y * f - o * 9.1)
        norm += amp
        amp *= gain
        f *= lac
    return out / norm


def ridged(noise, x, y, octaves=6, lac=2.05, gain=0.5, sharp=2.0):
    """Ridged multifractal in ~[0, 1]: sharp crests, each octave weighted by the one above (crisp peaks)."""
    amp, f, out, norm, w = 1.0, 1.0, 0.0, 0.0, 1.0
    for o in range(octaves):
        n = 1.0 - np.abs(noise(x * f + o * 31.7, y * f + o * 7.9))
        n = n ** sharp
        n = n * w
        w = np.clip(n * 1.6, 0.0, 1.0)
        out = out + amp * n
        norm += amp
        amp *= gain
        f *= lac
    return out / norm


def grid(n, size):
    """Cell-centre coordinates (X, Y) in metres for an n x n grid spanning `size` metres, centred on 0."""
    c = (np.arange(n) - (n - 1) / 2.0) * (size / (n - 1))
    return np.meshgrid(c, c, indexing='xy')


def smoothstep(a, b, v):
    t = np.clip((v - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------------------------------------- resampling
def _cubic_w(t):
    # Catmull-Rom weights for taps at -1, 0, 1, 2
    t2, t3 = t * t, t * t * t
    return (-0.5 * t3 + t2 - 0.5 * t, 1.5 * t3 - 2.5 * t2 + 1.0, -1.5 * t3 + 2.0 * t2 + 0.5 * t, 0.5 * t3 - 0.5 * t2)


def sample_bicubic(img, fr, fc):
    """Sample img at fractional (row, col) arrays with Catmull-Rom interpolation, clamped at the borders."""
    h, w = img.shape
    r0, c0 = np.floor(fr).astype(np.int64), np.floor(fc).astype(np.int64)
    tr, tc = fr - r0, fc - c0
    wr, wc = _cubic_w(tr), _cubic_w(tc)
    out = np.zeros(np.broadcast(fr, fc).shape, np.float64)
    for i in range(4):
        rr = np.clip(r0 + i - 1, 0, h - 1)
        row = np.zeros_like(out)
        for j in range(4):
            cc = np.clip(c0 + j - 1, 0, w - 1)
            row += wc[j] * img[rr, cc]
        out += wr[i] * row
    return out


def resize(img, n_out, cubic=True):
    """Resample a square grid to n_out x n_out (corner-aligned: edge samples map to edge samples)."""
    n_in = img.shape[0]
    t = np.linspace(0, n_in - 1, n_out)
    if not cubic:
        r0 = np.clip(np.floor(t).astype(int), 0, n_in - 2); f = t - r0
        a = img[r0] * (1 - f)[:, None] + img[r0 + 1] * f[:, None]
        return a[:, r0] * (1 - f)[None, :] + a[:, r0 + 1] * f[None, :]
    # separable Catmull-Rom (rows then columns) keeps memory low at 4k
    r0 = np.floor(t).astype(np.int64); tr = t - r0
    w = _cubic_w(tr)
    tmp = sum(w[i][:, None] * img[np.clip(r0 + i - 1, 0, n_in - 1)] for i in range(4))
    out = sum(w[i][None, :] * tmp[:, np.clip(r0 + i - 1, 0, n_in - 1)] for i in range(4))
    lo, hi = img.min(), img.max()
    return np.clip(out, lo, hi)


def blur(img, radius_cells, passes=3):
    """Approximate gaussian blur: repeated separable box filters via cumulative sums (edge-clamped)."""
    r = max(1, int(round(radius_cells / math.sqrt(passes))))
    out = img.astype(np.float64)
    for _ in range(passes):
        for axis in (0, 1):
            pad = [(0, 0), (0, 0)]; pad[axis] = (r + 1, r)
            p = np.pad(out, pad, mode='edge')
            c = np.cumsum(p, axis=axis)
            if axis == 0:
                out = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
            else:
                out = (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)
    return out


# ---------------------------------------------------------------------------------------------------------- distance
def distance_field(mask, dx):
    """Approximate Euclidean distance (metres) from every cell to the nearest True cell (chamfer, 2 passes).
    Rows are processed sequentially; each row's horizontal sweep is vectorised with a running minimum."""
    big = 1e9
    d = np.where(mask, 0.0, big)
    n, m = d.shape
    idx = np.arange(m, dtype=np.float64)

    def sweep_row(row):
        row = np.minimum(row, np.minimum.accumulate(row - idx) + idx)
        rev = row[::-1]
        rev = np.minimum(rev, np.minimum.accumulate(rev - idx) + idx)
        return rev[::-1]
    for i in range(n):
        if i > 0:
            p = d[i - 1]
            d[i] = np.minimum(d[i], p + 1.0)
            d[i, 1:] = np.minimum(d[i, 1:], p[:-1] + SQ2)
            d[i, :-1] = np.minimum(d[i, :-1], p[1:] + SQ2)
        d[i] = sweep_row(d[i])
    for i in range(n - 2, -1, -1):
        p = d[i + 1]
        d[i] = np.minimum(d[i], p + 1.0)
        d[i, 1:] = np.minimum(d[i, 1:], p[:-1] + SQ2)
        d[i, :-1] = np.minimum(d[i, :-1], p[1:] + SQ2)
        d[i] = sweep_row(d[i])
    return d * dx


def slope(h, dx):
    gy, gx = np.gradient(h, dx)
    return np.sqrt(gx * gx + gy * gy)


# ---------------------------------------------------------------------------------------------------------- hydraulic
def priority_flood(h, fixed, eps=1e-3):
    """Fill depressions so every non-fixed cell drains to a fixed cell (sea / border). Returns the filled copy.
    `eps` (metres) gives flats a tiny gradient so they drain instead of becoming lakes."""
    n, m = h.shape
    hf = h.astype(np.float64).ravel().tolist()
    closed = fixed.ravel().copy()
    # seed: fixed cells that touch a free cell
    free = ~fixed
    touch = np.zeros_like(fixed)
    touch[1:] |= free[:-1]; touch[:-1] |= free[1:]; touch[:, 1:] |= free[:, :-1]; touch[:, :-1] |= free[:, 1:]
    seeds = np.flatnonzero(fixed & touch)
    heap = [(hf[i], int(i)) for i in seeds]
    heapq.heapify(heap)
    closed = closed.tolist()
    offs = [dr * m + dc for dr, dc in NB]
    pop, push = heapq.heappop, heapq.heappush
    while heap:
        z, i = pop(heap)
        r, c = divmod(i, m)
        edge = r == 0 or c == 0 or r == n - 1 or c == m - 1
        for k, o in enumerate(offs):
            j = i + o
            if edge:
                rr, cc = r + NB[k][0], c + NB[k][1]
                if rr < 0 or cc < 0 or rr >= n or cc >= m:
                    continue
            if closed[j]:
                continue
            closed[j] = True
            zj = hf[j]
            if zj <= z:
                zj = z + eps
                hf[j] = zj
            push(heap, (zj, j))
    return np.array(hf).reshape(n, m)


def d8_receivers(h, fixed, dx, rng=None):
    """Receiver index and distance (metres) per cell; fixed cells / pits receive themselves.
    Without `rng`: steepest descent (D8). With `rng`: one downslope neighbour drawn with probability ~ slope^3
    (stochastic D8). Re-drawn every iteration this averages out D8's grid-aligned channels into natural meanders."""
    n, m = h.shape
    hp = np.pad(h, 1, mode='edge')
    rows, cols = np.mgrid[0:n, 0:m]
    S = np.zeros((8, n, m))
    for k, ((dr, dc), L) in enumerate(zip(NB, NB_LEN)):
        hn = hp[1 + dr:1 + dr + n, 1 + dc:1 + dc + m]
        s = (h - hn) / (L * dx)
        rr, cc = rows + dr, cols + dc
        valid = (rr >= 0) & (rr < n) & (cc >= 0) & (cc < m)
        S[k] = np.where(valid & (s > 0), s, 0.0)
    if rng is None:
        pick = np.argmax(S, axis=0)
    else:
        w = S ** 3.0
        c = np.cumsum(w, axis=0)
        u = rng.random((n, m)) * c[-1]
        pick = np.minimum((c < u[None]).sum(axis=0), 7)
    has = S.max(axis=0) > 0
    dr = np.array([d[0] for d in NB])[pick]; dc = np.array([d[1] for d in NB])[pick]
    L = np.array(NB_LEN)[pick]
    rcv = np.where(has & ~fixed, (rows + dr) * m + (cols + dc), rows * m + cols)
    dist = np.where(has, L * dx, dx)
    return rcv.ravel(), dist.ravel()


def drainage_area(h, rcv, cell_area, rain=None):
    """Upstream area (m^2) per cell, accumulated from high to low along the receivers."""
    order = np.argsort(h.ravel(), kind='stable')[::-1].tolist()
    acc = (np.full(h.size, cell_area) if rain is None else (rain.ravel() * cell_area)).tolist()
    r = rcv.tolist()
    for i in order:
        j = r[i]
        if j != i:
            acc[j] += acc[i]
    return np.array(acc).reshape(h.shape)


def stream_power(h, fixed, dx, uplift, iters, k=2e-5, m=0.45, dt=2000.0, rain=None, refill_every=8, log=None, seed=1, diffusion=0.0):
    """Implicit stream power erosion with uplift and hillslope diffusion: dh/dt = U - K A^m S + D lap(h).
    `uplift` in m/yr (array), `diffusion` D in m^2/yr; fixed cells stay put. Diffusion rounds off the smallest
    gullies so the channel network organises into a hierarchy (few big valleys, many small tributaries).
    Returns the eroded height and the final drainage area."""
    h = h.astype(np.float64).copy()
    n, mm = h.shape
    ca = dx * dx
    A = None
    rng = np.random.default_rng(seed)
    for it in range(iters):
        if it % refill_every == 0:
            h = priority_flood(h, fixed)
        h = np.where(fixed, h, h + uplift * dt)
        rcv, dist = d8_receivers(h, fixed, dx, rng)
        A = drainage_area(h, rcv, ca, rain)
        F = (k * dt * np.power(A.ravel(), m) / dist).tolist()
        hl = h.ravel().tolist()
        r = rcv.tolist()
        for i in np.argsort(h.ravel(), kind='stable').tolist():
            j = r[i]
            if j != i:
                f = F[i]
                hl[i] = (hl[i] + f * hl[j]) / (1.0 + f)
        h = np.array(hl).reshape(n, mm)
        if diffusion > 0.0:
            c = diffusion * dt / (dx * dx)
            steps = int(math.ceil(c / 0.2))
            for _ in range(steps):
                hp = np.pad(h, 1, mode='edge')
                lap = hp[:-2, 1:-1] + hp[2:, 1:-1] + hp[1:-1, :-2] + hp[1:-1, 2:] - 4.0 * h
                h = np.where(fixed, h, h + (c / steps) * lap)
        if log and (it % 20 == 0 or it == iters - 1):
            log('  stream power %d/%d  max %.1f' % (it + 1, iters, h.max()))
    return h, A


def thermal(h, dx, talus_deg, iters, rate=0.25, mask=None):
    """Thermal weathering: material above the talus angle slides to lower neighbours (vectorised, 8 neighbours)."""
    t = math.tan(math.radians(talus_deg)) * dx
    h = h.astype(np.float64).copy()
    for _ in range(iters):
        hp = np.pad(h, 1, mode='edge')
        n, m = h.shape
        diffs = []
        for (dr, dc), L in zip(NB, NB_LEN):
            d = h - hp[1 + dr:1 + dr + n, 1 + dc:1 + dc + m] - t * L
            diffs.append(np.maximum(d, 0.0))
        tot = sum(diffs)
        mx = np.maximum.reduce(diffs)
        move = rate * mx * 0.5
        if mask is not None:
            move = move * mask
        frac = np.where(tot > 0, move / np.maximum(tot, 1e-9), 0.0)
        delta = -move
        for (dr, dc), d in zip(NB, diffs):
            give = np.pad(frac * d, 1)
            # material given to neighbour (r+dr, c+dc) arrives there: shift back
            delta += give[1 - dr:1 - dr + n, 1 - dc:1 - dc + m]
        h += delta
    return h


# ---------------------------------------------------------------------------------------------------------- output
def to_uint16(h_m, z_scale):
    """Unreal landscape encoding: Z(cm) = (v - 32768) * z_scale / 128  ->  v = 32768 + h * 100 * 128 / z_scale."""
    v = 32768.0 + h_m * (100.0 * 128.0 / z_scale)
    return np.clip(np.round(v), 0, 65535).astype(np.uint16)


def z_scale_for(h_m, margin=1.05):
    """Smallest landscape Z scale (cm per 1/128 step... i.e. actor scale Z) that fits the height range."""
    span = max(abs(float(h_m.max())), abs(float(h_m.min()))) * margin
    return max(span * 100.0 / 256.0, 10.0)  # actor Z scale: +-256 * scale/100 m range


def preview_rgb(h, dx, sea_rgb=(18, 50, 90)):
    """Hillshaded colour preview (uint8 RGB) for eyeballing the generated terrain."""
    gy, gx = np.gradient(h, dx)
    nx, ny, nz = -gx, -gy, np.ones_like(h)
    L = np.array([-0.6, -0.5, 0.62]); L /= np.linalg.norm(L)
    shade = np.clip((nx * L[0] + ny * L[1] + nz * L[2]) / np.sqrt(nx * nx + ny * ny + 1), 0, 1)
    hn = np.clip(h / max(h.max(), 1.0), 0, 1)
    base = np.stack([0.35 + 0.5 * hn, 0.42 + 0.35 * hn, 0.25 + 0.6 * hn], -1)
    rgb = base * (0.25 + 0.85 * shade[..., None])
    rgb = np.where((h <= 0)[..., None], np.array(sea_rgb) / 255.0 * (0.6 + 0.4 * np.clip(1 + h / 80, 0, 1))[..., None], rgb)
    return (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
