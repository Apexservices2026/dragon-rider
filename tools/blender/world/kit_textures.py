"""Procedural texture generation for the Viking prop kit.

Every texture is computed in numpy from spectrally filtered noise (FFT noise is
periodic, so every tiling texture is seamless by construction) and saved as PNG.
Nothing here relies on Blender procedural shader nodes, so the results are plain
image textures that Unreal and three.js can read.

Outputs per material: <T>_BC.png (sRGB base colour), <T>_N.png (OpenGL / +Y
tangent-space normal, used by Blender + glTF), <T>_N_DX.png (DirectX / -Y green,
for Unreal), <T>_R.png (linear roughness).
"""
import math
import os

import numpy as np

RNG_SEED = 1209


# --------------------------------------------------------------------------- noise
def fnoise(n, beta=1.0, fmin=1.0, fmax=None, ax=1.0, ay=1.0, seed=0):
    """Tileable fractal noise. ax/ay > 1 squash features along that axis."""
    rng = np.random.default_rng(RNG_SEED + seed * 7919)
    white = rng.standard_normal((n, n))
    F = np.fft.fft2(white)
    fx = np.fft.fftfreq(n) * n
    fy = np.fft.fftfreq(n) * n
    KX, KY = np.meshgrid(fx, fy)          # rows = v (y), cols = u (x)
    k = np.sqrt((KX * ax) ** 2 + (KY * ay) ** 2)
    k[0, 0] = 1e9
    filt = 1.0 / np.power(np.maximum(k, 1e-6), beta)
    filt *= 1.0 - np.exp(-(k / max(fmin, 1e-3)) ** 2)
    if fmax:
        filt *= np.exp(-(k / fmax) ** 2)
    out = np.real(np.fft.ifft2(F * filt))
    out -= out.mean()
    out /= out.std() + 1e-9
    return out


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = t[..., None] if np.ndim(t) == 2 else t
    return a * (1 - t) + b * t


def col(c, shape):
    return np.broadcast_to(np.array(c, dtype=np.float64), shape + (3,)).copy()


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5 * strength
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5 * strength
    n = np.stack([-dx, -dy, np.ones_like(h)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def voronoi(n, count, seed, jitter=1.0):
    """Periodic Worley noise: returns (F1 distance, F2 distance, cell id) in pixels/n."""
    rng = np.random.default_rng(RNG_SEED + 31 * seed)
    pts = rng.random((count, 2))
    ys, xs = np.mgrid[0:n, 0:n] / n
    f1 = np.full((n, n), 9.0)
    f2 = np.full((n, n), 9.0)
    cid = np.zeros((n, n), dtype=np.int32)
    for i, (px, py) in enumerate(pts):
        dx = np.abs(xs - px)
        dx = np.minimum(dx, 1 - dx)
        dy = np.abs(ys - py)
        dy = np.minimum(dy, 1 - dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < f1
        f2 = np.where(closer, f1, np.minimum(f2, d))
        cid = np.where(closer, i, cid)
        f1 = np.where(closer, d, f1)
    return f1, f2, cid


# --------------------------------------------------------------------------- materials
def tex_wood(n):
    """Weathered timber, grain runs along V. Tile = 2 m."""
    fibre = fnoise(n, beta=0.9, fmin=6, fmax=n / 3, ax=1, ay=14, seed=1)
    warp = fnoise(n, beta=1.6, fmin=1, fmax=40, ax=1, ay=4, seed=2)
    u = np.arange(n)[None, :] / n
    rings = np.sin(2 * math.pi * (u * 22 + warp * 0.35 + fibre * 0.015))
    tone = fnoise(n, beta=2.0, fmin=1, fmax=12, ax=1, ay=2.5, seed=3)
    blotch = fnoise(n, beta=1.4, fmin=3, fmax=80, seed=4)
    crack_n = fnoise(n, beta=0.7, fmin=10, fmax=n / 2, ax=1, ay=40, seed=5)
    crack = sstep(2.1, 2.9, crack_n) * sstep(-0.2, 0.6, blotch)
    # knots
    rng = np.random.default_rng(RNG_SEED + 77)
    ys, xs = np.mgrid[0:n, 0:n] / n
    knot = np.zeros((n, n))
    for _ in range(5):
        kx, ky = rng.random(2)
        dx = np.minimum(np.abs(xs - kx), 1 - np.abs(xs - kx))
        dy = np.minimum(np.abs(ys - ky), 1 - np.abs(ys - ky))
        r = np.sqrt((dx * 3.0) ** 2 + (dy * 0.9) ** 2) * 55
        knot = np.maximum(knot, np.exp(-r * r))
    sh = (n, n)
    silver = col((0.27, 0.245, 0.21), sh)
    brown = col((0.24, 0.165, 0.105), sh)
    dark = col((0.16, 0.12, 0.09), sh)
    c = mix(brown, silver, sstep(-1.2, 1.2, tone))
    c *= (0.86 + 0.08 * rings + 0.07 * fibre + 0.05 * blotch)[..., None]
    c = mix(c, dark, np.clip(knot * 0.9, 0, 1))
    c = mix(c, dark * 0.6, crack)
    h = 0.25 * fibre + 0.35 * rings * 0.5 - 1.6 * crack - 0.8 * knot + 0.15 * blotch
    nrm = normal_from_height(h, 2.2)
    r = np.clip(0.78 + 0.06 * fibre + 0.05 * tone + 0.12 * crack, 0, 1)
    return c, nrm, r


def tex_tar(n):
    """Tar-blackened hull planking (pine tar over oak). Grain along V. Tile = 2 m."""
    fibre = fnoise(n, beta=0.9, fmin=6, fmax=n / 3, ax=1, ay=14, seed=11)
    warp = fnoise(n, beta=1.6, fmin=1, fmax=40, ax=1, ay=4, seed=12)
    u = np.arange(n)[None, :] / n
    rings = np.sin(2 * math.pi * (u * 18 + warp * 0.4))
    wear = fnoise(n, beta=1.5, fmin=2, fmax=60, ax=1, ay=2, seed=13)
    drip = fnoise(n, beta=1.2, fmin=4, fmax=120, ax=6, ay=1, seed=14)  # vertical runs
    sh = (n, n)
    tar = col((0.075, 0.055, 0.038), sh)
    worn = col((0.19, 0.125, 0.075), sh)
    c = mix(tar, worn, sstep(1.4, 2.8, wear + 0.3 * fibre) * 0.7)
    c *= (0.9 + 0.06 * rings + 0.08 * fibre + 0.04 * drip)[..., None]
    h = 0.3 * fibre + 0.2 * rings - 0.25 * drip
    nrm = normal_from_height(h, 1.6)
    r = np.clip(0.42 + 0.08 * fibre + 0.22 * sstep(0.6, 2.0, wear) + 0.05 * drip, 0, 1)
    return c, nrm, r


def tex_turf(n):
    """Thick, mossy sod roof / grass. Tile = 4 m."""
    big = fnoise(n, beta=2.0, fmin=1, fmax=10, seed=21)
    mid = fnoise(n, beta=1.3, fmin=4, fmax=90, seed=22)
    clump = fnoise(n, beta=0.8, fmin=30, fmax=n / 4, seed=23)
    blade = fnoise(n, beta=0.4, fmin=80, fmax=n / 1.5, ax=1, ay=2.5, seed=24)
    sh = (n, n)
    green = col((0.17, 0.25, 0.075), sh)
    dry = col((0.30, 0.29, 0.12), sh)
    moss = col((0.10, 0.17, 0.055), sh)
    soil = col((0.17, 0.12, 0.07), sh)
    c = mix(green, dry, sstep(0.4, 2.0, big + 0.4 * mid) * 0.8)
    c = mix(c, moss, sstep(0.4, 1.4, -big + 0.5 * mid) * 0.8)
    c = mix(c, soil, sstep(1.6, 2.6, -mid - 0.6 * clump) * 0.85)
    c *= (0.82 + 0.10 * clump + 0.10 * blade)[..., None]
    h = 0.6 * mid + 0.7 * clump + 0.45 * blade
    nrm = normal_from_height(h, 2.6)
    r = np.clip(0.88 + 0.05 * blade, 0, 1)
    return c, nrm, r


def tex_iron(n):
    """Hand-forged iron with rust. Tile = 1 m."""
    rust_n = fnoise(n, beta=1.4, fmin=2, fmax=80, seed=31)
    pits = fnoise(n, beta=0.5, fmin=60, fmax=n / 2, seed=32)
    hammer_f1, _, _ = voronoi(n, 90, seed=33)
    sh = (n, n)
    iron = col((0.085, 0.085, 0.09), sh)
    rust = col((0.34, 0.15, 0.06), sh)
    rmask = sstep(0.3, 1.3, rust_n + 0.3 * pits)
    c = mix(iron, rust, rmask)
    c *= (0.9 + 0.1 * pits)[..., None]
    h = -hammer_f1 * 18 + 0.25 * pits * rmask
    nrm = normal_from_height(h, 3.0)
    r = np.clip(0.48 + 0.4 * rmask + 0.05 * pits, 0, 1)
    return c, nrm, r


def tex_stone(n):
    """Field-stone footing / forge stones with lichen. Tile = 2 m."""
    f1, f2, cid = voronoi(n, 46, seed=41)
    edge = f2 - f1
    lich = fnoise(n, beta=1.2, fmin=6, fmax=150, seed=42)
    grain = fnoise(n, beta=0.6, fmin=40, fmax=n / 2, seed=43)
    rng = np.random.default_rng(RNG_SEED + 44)
    tint = rng.random((cid.max() + 1, 3)) * 0.07
    sh = (n, n)
    base = col((0.33, 0.32, 0.30), sh) + tint[cid]
    gap = col((0.10, 0.085, 0.06), sh)
    lichen = col((0.48, 0.47, 0.30), sh)
    dome = sstep(0.0, 0.045, edge)
    c = mix(gap, base, dome)
    c = mix(c, lichen, sstep(1.4, 2.2, lich) * dome * 0.8)
    c *= (0.9 + 0.08 * grain)[..., None]
    h = np.sqrt(np.clip(edge, 0, 0.08) / 0.08) * 2.0 + 0.1 * grain
    nrm = normal_from_height(h, 6.0)
    r = np.clip(0.82 + 0.08 * grain + 0.06 * (1 - dome), 0, 1)
    return c, nrm, r


def cloth_detail(n, threads=260):
    """Shared wool weave normal/roughness (sail + banners)."""
    u = np.arange(n)[None, :] / n
    v = np.arange(n)[:, None] / n
    weave = np.sin(2 * math.pi * u * threads) * np.sin(2 * math.pi * v * threads)
    wrinkle = fnoise(n, beta=1.6, fmin=2, fmax=60, ax=1, ay=3, seed=51)
    fuzz = fnoise(n, beta=0.3, fmin=100, fmax=n / 2, seed=52)
    h = 0.35 * weave + 0.9 * wrinkle + 0.15 * fuzz
    nrm = normal_from_height(h, 1.4)
    r = np.clip(0.92 + 0.04 * fuzz, 0, 1)
    return nrm, r, wrinkle, fuzz


CLANS = {
    # clan: (primary, secondary, accent)
    "ClanA": ((0.56, 0.075, 0.05), (0.86, 0.80, 0.66), (0.06, 0.05, 0.045)),
    "ClanB": ((0.10, 0.19, 0.44), (0.80, 0.57, 0.18), (0.06, 0.05, 0.045)),
}


def tex_sail(n, clan, wrinkle, fuzz):
    """Square sail, UV 0..1 covers the whole sail (u across, v up). Vertical stripes."""
    p, s, _ = CLANS[clan]
    u = np.arange(n)[None, :] / n * np.ones((n, 1))
    v = np.arange(n)[:, None] / n * np.ones((1, n))
    stripes = 8
    band = (np.floor(u * stripes).astype(int) % 2) == 0
    # soft stripe edge with slight weave wobble
    sh = (n, n)
    c = np.where(band[..., None], col(p, sh), col(s, sh))
    border = (u < 0.012) | (u > 0.988) | (v < 0.015) | (v > 0.985)
    c = np.where(border[..., None], c * 0.55, c)
    dirt = sstep(0.35, 0.0, v) * 0.25 + 0.06 * fuzz
    c *= (1 - dirt)[..., None]
    c *= (0.93 + 0.05 * wrinkle + 0.03 * fuzz)[..., None]
    fade = fnoise(n, beta=2, fmin=1, fmax=8, seed=53)
    c = mix(c, col((0.78, 0.72, 0.6), sh), np.clip(0.08 + 0.06 * fade, 0, 0.25))
    return c


def _triskele(r, a, arms=3, twist=2.4, width=0.42):
    phase = (a * arms / (2 * math.pi) + r * twist) % 1.0
    return (phase < width) & (r > 0.16) & (r < 0.86)


def _shield_design(idx, r, a, x, y, pal):
    p, s, k = pal
    sh = r.shape
    c1, c2, c3 = col(p, sh), col(s, sh), col(k, sh)
    d = idx % 8
    swap = idx >= 8
    if swap:
        c1, c2 = c2, c1
    if d == 0:
        m = np.zeros(sh, bool)
    elif d == 1:
        m = x > 0
    elif d == 2:
        m = (x > 0) ^ (y > 0)
    elif d == 3:
        m = (np.floor(a / (2 * math.pi) * 8).astype(int) % 2) == 0
    elif d == 4:
        m = _triskele(r, a, arms=4, twist=1.6, width=0.5)
    elif d == 5:
        m = (np.abs(x) < 0.17) | (np.abs(y) < 0.17)
    elif d == 6:
        m = (r > 0.45) & (r < 0.7)
    else:
        m = _triskele(r, a, arms=3, twist=2.2, width=0.45)
    out = np.where(m[..., None], c2, c1)
    if d in (0, 6):
        ring = (r > 0.80) & (r < 0.88)
        out = np.where(ring[..., None], c3, out)
    return out


def tex_shields(n, clan):
    """4x4 atlas of 16 painted round shields. Cell centre = boss, cell edge = rim."""
    cells = 4
    cs = n // cells
    pal = CLANS[clan]
    sh = (n, n)
    c = np.zeros(sh + (3,))
    plank_n = fnoise(n, beta=1.0, fmin=4, fmax=120, ax=1, ay=8, seed=61)
    chip = fnoise(n, beta=0.9, fmin=8, fmax=200, seed=62)
    wear = fnoise(n, beta=1.8, fmin=1, fmax=16, seed=63)
    wood = col((0.40, 0.30, 0.19), sh) * (0.85 + 0.1 * plank_n)[..., None]
    ys, xs = np.mgrid[0:cs, 0:cs]
    lx = (xs + 0.5) / cs * 2 - 1
    ly = (ys + 0.5) / cs * 2 - 1
    lr = np.sqrt(lx * lx + ly * ly) / 0.96
    la = np.arctan2(ly, lx) % (2 * math.pi)
    for j in range(cells):
        for i in range(cells):
            idx = j * cells + i
            design = _shield_design(idx, lr, la, lx, ly, pal)
            c[j * cs:(j + 1) * cs, i * cs:(i + 1) * cs] = design
    # planks: horizontal seams across every shield (6 boards each)
    v = (np.arange(n)[:, None] / n * np.ones((1, n)))
    seam = np.abs(((v * cells * 6) % 1.0) - 0.5) > 0.48
    chipped = sstep(1.5, 2.1, chip + 0.6 * wear)
    c = mix(c, wood, np.clip(chipped + seam * 0.6, 0, 1))
    c *= (0.9 + 0.06 * plank_n - 0.05 * wear)[..., None]
    # rim (rawhide edging) and boss shadow per cell
    ys, xs = np.mgrid[0:n, 0:n]
    gx = ((xs % cs) + 0.5) / cs * 2 - 1
    gy = ((ys % cs) + 0.5) / cs * 2 - 1
    gr = np.sqrt(gx * gx + gy * gy) / 0.96
    rim = gr > 0.93
    c = np.where(rim[..., None], col((0.20, 0.13, 0.07), sh), c)
    c = np.where((gr < 0.22)[..., None], c * 0.45, c)
    h = -1.2 * seam - 0.6 * chipped + 0.6 * rim + 0.15 * plank_n
    nrm = normal_from_height(h, 1.6)
    r = np.clip(0.62 + 0.2 * chipped + 0.08 * wear + 0.1 * rim, 0, 1)
    return c, nrm, r


def tex_banner(n, clan, wrinkle, fuzz):
    """Banner cloth, UV 0..1 (u across, v up; tails at v=0). Emblem centred high."""
    p, s, k = CLANS[clan]
    sh = (n, n)
    u = np.arange(n)[None, :] / n * np.ones((n, 1))
    v = np.arange(n)[:, None] / n * np.ones((1, n))
    c = col(p, sh)
    border = (u < 0.07) | (u > 0.93) | (v > 0.95)
    c = np.where(border[..., None], col(s, sh), c)
    x = (u - 0.5) * 2.0
    y = (v - 0.62) * 2.0 * 1.6
    r = np.sqrt(x * x + y * y) / 0.78
    a = np.arctan2(y, x) % (2 * math.pi)
    if clan == "ClanA":
        emb = _triskele(r, a, arms=3, twist=1.9, width=0.4) | ((r > 0.9) & (r < 1.0))
    else:
        spokes = (np.abs(((a / (2 * math.pi) * 8 + 0.5) % 1.0) - 0.5) < 0.06) & (r < 0.95) & (r > 0.12)
        bars = (np.abs(r - 0.78) < 0.05) & (np.abs(((a / (2 * math.pi) * 8 + 0.5) % 1.0) - 0.5) < 0.17)
        emb = spokes | bars | (r < 0.14)
    c = np.where(emb[..., None], col(s, sh), c)
    c *= (0.92 + 0.05 * wrinkle + 0.03 * fuzz)[..., None]
    return c


# --------------------------------------------------------------------------- save
def _to_image(bpy, name, arr, n, srgb, path):
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.new(name, n, n, alpha=False, float_buffer=False)
    rgba = np.ones((n, n, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1) if arr.ndim == 3 else np.clip(arr, 0, 1)[..., None]
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    return img


def srgb_encode(lin):
    """Base colours above are authored as linear reflectance; store as sRGB."""
    lin = np.clip(lin, 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


def build_all(bpy, outdir, hi=2048, lo=1024):
    """Generate every kit texture; returns {texture_set: {map: bpy image}}."""
    os.makedirs(outdir, exist_ok=True)
    sets = {}

    def save_set(tname, n, c, nrm, r, extra=None):
        d = {}
        if c is not None:
            d["BC"] = _to_image(bpy, f"{tname}_BC", srgb_encode(c), n, True, os.path.join(outdir, f"{tname}_BC.png"))
        d["N"] = _to_image(bpy, f"{tname}_N", nrm, n, False, os.path.join(outdir, f"{tname}_N.png"))
        dx = nrm.copy()
        dx[..., 1] = 1.0 - dx[..., 1]
        _to_image(bpy, f"{tname}_N_DX", dx, n, False, os.path.join(outdir, f"{tname}_N_DX.png"))
        d["R"] = _to_image(bpy, f"{tname}_R", r, n, False, os.path.join(outdir, f"{tname}_R.png"))
        d["size"] = n
        sets[tname] = d

    for tname, fn, n in (("T_Wood", tex_wood, hi), ("T_WoodTar", tex_tar, hi), ("T_Turf", tex_turf, hi),
                         ("T_Iron", tex_iron, lo), ("T_Stone", tex_stone, lo)):
        c, nrm, r = fn(n)
        save_set(tname, n, c, nrm, r)
        print("TEX", tname, n)

    cn, cr, wr, fz = cloth_detail(lo)
    sets["T_Cloth"] = {}
    # shared cloth normal / roughness
    sets["T_Cloth"]["N"] = _to_image(bpy, "T_Cloth_N", cn, lo, False, os.path.join(outdir, "T_Cloth_N.png"))
    dx = cn.copy()
    dx[..., 1] = 1.0 - dx[..., 1]
    _to_image(bpy, "T_Cloth_N_DX", dx, lo, False, os.path.join(outdir, "T_Cloth_N_DX.png"))
    sets["T_Cloth"]["R"] = _to_image(bpy, "T_Cloth_R", cr, lo, False, os.path.join(outdir, "T_Cloth_R.png"))
    sets["T_Cloth"]["size"] = lo
    for clan in CLANS:
        sets[f"T_Sail_{clan}"] = {"BC": _to_image(bpy, f"T_Sail_{clan}_BC", srgb_encode(tex_sail(lo, clan, wr, fz)), lo, True,
                                                   os.path.join(outdir, f"T_Sail_{clan}_BC.png")), "size": lo}
        sets[f"T_Banner_{clan}"] = {"BC": _to_image(bpy, f"T_Banner_{clan}_BC", srgb_encode(tex_banner(lo, clan, wr, fz)), lo, True,
                                                     os.path.join(outdir, f"T_Banner_{clan}_BC.png")), "size": lo}
        c, nrm, r = tex_shields(hi, clan)
        if clan == "ClanA":   # normal + roughness are identical for both clans
            save_set("T_Shields", hi, None, nrm, r)
        sets[f"T_Shields_{clan}"] = {"BC": _to_image(bpy, f"T_Shields_{clan}_BC", srgb_encode(c), hi, True,
                                                     os.path.join(outdir, f"T_Shields_{clan}_BC.png")), "size": hi}
        print("TEX clan", clan)
    return sets
