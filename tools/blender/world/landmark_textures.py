"""Procedural textures for the archipelago landmark set (stronghold, rune circle, dragon lair,
waterfall, coastal dressing). numpy + periodic FFT noise, saved as PNG next to the kit textures.

Per material: <T>_BC.png (sRGB; RGBA for the water/foam cards), <T>_N.png (OpenGL), <T>_N_DX.png
(DirectX, Unreal), <T>_R.png (roughness) and, where it glows, <T>_E.png (emissive colour, sRGB).
"""
import math
import os

import numpy as np

from kit_textures import (col, fnoise, mix, normal_from_height, sstep, srgb_encode, voronoi)


def _save(bpy, name, arr, n, srgb, path, alpha=None, h=None):
    h = h or n
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, n, h, alpha=alpha is not None, float_buffer=False)
    rgba = np.ones((h, n, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1) if arr.ndim == 3 else np.clip(arr, 0, 1)[..., None]
    if alpha is not None:
        rgba[..., 3] = np.clip(alpha, 0, 1)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    if alpha is not None:
        img.alpha_mode = "STRAIGHT"
    return img


# --------------------------------------------------------------------------- materials
def tex_shingle(n):
    """Tarred wooden 'dragon-scale' shingles, rows along U, slope up = +V. Tile 2 m (12 x 8 shingles)."""
    cols, rows = 12, 8
    u = (np.arange(n)[None, :] + 0.5) / n * np.ones((n, 1))
    v = (np.arange(n)[:, None] + 0.5) / n * np.ones((1, n))
    r = np.floor(v * rows).astype(int)
    b = v * rows - r
    cu = u * cols + 0.5 * (r % 2)
    ci = np.floor(cu).astype(int) % cols
    a = cu - np.floor(cu)
    edge = 0.38 * (1 - np.sqrt(np.clip(1 - (2 * a - 1) ** 2, 0, 1)))
    inside = b >= edge
    gap = (a < 0.025) | (a > 0.975)
    rng = np.random.default_rng(301)
    tint = rng.random((rows, cols))
    t = tint[r % rows, ci]
    grain = fnoise(n, beta=0.9, fmin=8, fmax=n / 3, ax=1, ay=10, seed=302)
    moss_n = fnoise(n, beta=1.6, fmin=1, fmax=30, seed=303)
    sh = (n, n)
    dark = col((0.06, 0.04, 0.028), sh)
    light = col((0.19, 0.125, 0.075), sh)
    c = mix(dark, light, np.clip(t * 0.8 + 0.1 * grain, 0, 1))
    c = mix(c, col((0.09, 0.12, 0.04), sh), sstep(1.5, 2.4, moss_n) * 0.7)
    c = np.where(inside[..., None], c, c * 0.35)
    c = np.where(gap[..., None], c * 0.4, c)
    h = np.where(inside, 1.0 - 0.7 * b, 0.0) + 0.06 * grain - 0.5 * gap
    nrm = normal_from_height(h, 7.0)
    rr = np.clip(0.62 + 0.12 * t + 0.05 * grain + 0.15 * (~inside), 0, 1)
    return c, nrm, rr


def _rock_base(n, seed, cells=60):
    f1, f2, _ = voronoi(n, cells, seed=seed)
    crack = 1 - sstep(0.0, 0.005, f2 - f1)
    crack *= sstep(0.3, 1.2, fnoise(n, beta=1.5, fmin=2, fmax=30, seed=seed + 9))   # only some cracks open
    big = fnoise(n, beta=2.0, fmin=1, fmax=16, seed=seed + 1)
    mid = fnoise(n, beta=1.2, fmin=6, fmax=120, seed=seed + 2)
    fine = fnoise(n, beta=0.5, fmin=60, fmax=n / 2, seed=seed + 3)
    return crack, big, mid, fine


def tex_rock(n):
    """Grey gneiss/granite boulders with lichen. Tile 4 m."""
    crack, big, mid, fine = _rock_base(n, 401)
    lich = fnoise(n, beta=1.1, fmin=8, fmax=200, seed=405)
    sh = (n, n)
    v = (np.arange(n)[:, None] / n) * np.ones((1, n))
    strata = np.sin(2 * math.pi * (v * 9 + 0.25 * big + 0.1 * mid))
    c = mix(col((0.17, 0.165, 0.16), sh), col((0.32, 0.31, 0.29), sh), sstep(-1.5, 1.5, big + 0.5 * mid + 0.3 * strata))
    c *= (0.9 + 0.07 * fine)[..., None]
    c = mix(c, col((0.36, 0.36, 0.22), sh), sstep(1.5, 2.3, lich) * 0.8)
    c = mix(c, col((0.11, 0.15, 0.06), sh), sstep(1.9, 2.6, -lich + 0.4 * big) * 0.7)
    c = mix(c, col((0.07, 0.065, 0.06), sh), crack * 0.6)
    h = 0.5 * mid + 0.25 * big + 0.12 * fine - 0.7 * crack + 0.15 * strata
    nrm = normal_from_height(h, 4.0)
    r = np.clip(0.86 + 0.05 * fine - 0.06 * sstep(1.5, 2.3, lich), 0, 1)
    return c, nrm, r, crack, mid


def tex_rock_frost(n, crack, mid):
    """Base colour variant of T_Rock: hoar frost in cracks and hollows (shares T_Rock N/R)."""
    c, _, _, _, _ = tex_rock(n)
    sh = (n, n)
    frost = np.clip(crack * 1.0 + sstep(0.2, 1.2, -mid) * 0.75, 0, 1)
    speck = sstep(1.8, 2.4, fnoise(n, beta=0.4, fmin=80, fmax=n / 2, seed=411))
    c = mix(c * 1.15, col((0.72, 0.78, 0.85), sh), np.clip(frost + speck * 0.6, 0, 1))
    return c


def tex_lava(n):
    """Porous black basalt with glowing magma cracks. Tile 2 m. Returns emissive."""
    f1, f2, _ = voronoi(n, 38, seed=421)
    crack = 1 - sstep(0.0, 0.008, f2 - f1)
    pits = sstep(1.6, 2.4, fnoise(n, beta=0.5, fmin=60, fmax=n / 3, seed=422))
    mid = fnoise(n, beta=1.2, fmin=4, fmax=100, seed=423)
    heat = sstep(1.3, 2.3, fnoise(n, beta=1.8, fmin=1, fmax=10, seed=424))
    sh = (n, n)
    c = mix(col((0.022, 0.02, 0.019), sh), col((0.07, 0.062, 0.055), sh), sstep(-1, 1.5, mid))
    c = mix(c, col((0.01, 0.01, 0.01), sh), pits * 0.8)
    c = mix(c, col((0.25, 0.04, 0.01), sh), crack * heat)
    h = 0.35 * mid - 0.9 * pits - 1.4 * crack
    nrm = normal_from_height(h, 4.0)
    r = np.clip(0.9 - 0.3 * crack * heat, 0, 1)
    e = col((1.0, 0.32, 0.05), sh) * (crack * heat * (0.6 + 0.4 * sstep(-1, 1, mid)))[..., None]
    return c, nrm, r, e


def tex_obsidian(n):
    """Volcanic glass: glossy black, conchoidal facets, thin ember veins. Tile 2 m. Returns emissive."""
    f1, f2, _ = voronoi(n, 70, seed=431)
    facet = np.sqrt(np.clip(f2 - f1, 0, 0.06) / 0.06)
    vein_n = fnoise(n, beta=1.3, fmin=2, fmax=80, ax=1, ay=3, seed=432)
    vein = 1 - sstep(0.0, 0.06, np.abs(vein_n))
    mask = sstep(1.5, 2.4, fnoise(n, beta=1.8, fmin=1, fmax=12, seed=433))
    sheen = fnoise(n, beta=1.6, fmin=2, fmax=40, ax=1, ay=6, seed=434)
    sh = (n, n)
    c = mix(col((0.012, 0.011, 0.013), sh), col((0.03, 0.022, 0.04), sh), sstep(0, 2, sheen))
    c = mix(c, col((0.3, 0.06, 0.01), sh), vein * mask)
    h = 1.2 * facet - 0.6 * vein * mask
    nrm = normal_from_height(h, 5.0)
    r = np.clip(0.1 + 0.15 * (1 - facet) + 0.25 * vein * mask, 0, 1)
    e = col((1.0, 0.38, 0.06), sh) * (vein * mask)[..., None]
    return c, nrm, r, e


def tex_crystal(n):
    """Ember crystal: unique UV per crystal, v = 0 at the base .. 1 at the tip. Returns emissive."""
    u = (np.arange(n)[None, :] + 0.5) / n * np.ones((n, 1))
    v = (np.arange(n)[:, None] + 0.5) / n * np.ones((1, n))
    frac = fnoise(n, beta=1.0, fmin=3, fmax=90, ax=3, ay=1, seed=441)
    lines = 1 - sstep(0.0, 0.08, np.abs(fnoise(n, beta=1.2, fmin=2, fmax=50, ax=1, ay=4, seed=442)))
    sh = (n, n)
    c = mix(col((0.08, 0.012, 0.006), sh), col((0.5, 0.12, 0.02), sh), np.clip(v * 0.8 + 0.1 * frac, 0, 1))
    glow = np.clip(0.15 + 0.85 * v ** 1.6 + 0.25 * lines + 0.1 * frac, 0, 1.2)
    e = mix(col((0.55, 0.06, 0.01), sh), col((1.0, 0.55, 0.12), sh), np.clip(v, 0, 1)) * glow[..., None]
    h = 0.4 * frac + 0.6 * lines
    nrm = normal_from_height(h, 2.0)
    r = np.clip(0.06 + 0.06 * frac, 0, 1)
    return c, nrm, r, e


def tex_bone(n):
    """Weathered dragon bone. Tile 1 m, fibres along V."""
    fib = fnoise(n, beta=0.9, fmin=6, fmax=n / 3, ax=1, ay=10, seed=451)
    stain = fnoise(n, beta=1.6, fmin=1, fmax=30, seed=452)
    pores = sstep(2.0, 2.7, fnoise(n, beta=0.4, fmin=90, fmax=n / 2, seed=453))
    crack = 1 - sstep(0.0, 0.05, np.abs(fnoise(n, beta=1.0, fmin=3, fmax=120, ax=1, ay=6, seed=454)))
    crack *= sstep(0.5, 1.5, stain)
    sh = (n, n)
    c = mix(col((0.62, 0.56, 0.44), sh), col((0.36, 0.27, 0.17), sh), sstep(0.3, 2.0, stain) * 0.8)
    c *= (0.92 + 0.06 * fib)[..., None]
    c = mix(c, col((0.12, 0.09, 0.06), sh), np.clip(pores * 0.6 + crack * 0.9, 0, 1))
    h = 0.3 * fib - 0.6 * pores - 1.0 * crack
    nrm = normal_from_height(h, 2.5)
    r = np.clip(0.62 + 0.1 * fib + 0.15 * crack, 0, 1)
    return c, nrm, r


def tex_charred(n):
    """Charred timber with alligator cracking; embers glow in some cracks. Tile 2 m, grain along V."""
    rng = np.random.default_rng(461)
    # stretched cells: compute voronoi on a 1:3 aspect grid by sampling a narrow tile repeated
    f1, f2, _ = voronoi(n, 160, seed=462)
    f1b = np.roll(f1, n // 7, axis=0)
    crack = 1 - sstep(0.0, 0.01, f2 - f1)
    grain = fnoise(n, beta=0.9, fmin=6, fmax=n / 3, ax=1, ay=12, seed=463)
    gcrack = 1 - sstep(0.0, 0.04, np.abs(grain))
    heat = sstep(1.0, 2.0, fnoise(n, beta=1.8, fmin=1, fmax=10, seed=464))
    dome = np.sqrt(np.clip(f2 - f1, 0, 0.05) / 0.05)
    sh = (n, n)
    c = mix(col((0.012, 0.011, 0.01), sh), col((0.075, 0.07, 0.065), sh), dome * (0.5 + 0.5 * sstep(-1, 1, grain)))
    crk = np.clip(crack + 0.6 * gcrack, 0, 1)
    c = mix(c, col((0.2, 0.03, 0.005), sh), crk * heat)
    h = 1.0 * dome - 0.8 * crk + 0.1 * grain + 0 * f1b
    nrm = normal_from_height(h, 4.0)
    r = np.clip(0.9 - 0.25 * crk * heat, 0, 1)
    e = col((1.0, 0.3, 0.04), sh) * (crk * heat)[..., None] * 0.9
    _ = rng
    return c, nrm, r, e


def tex_ice(n):
    """Glacier ice: blue depth variation, white fracture planes, trapped bubbles. Tile 2 m. Emissive = faint
    inner glow for the shrine."""
    depth = fnoise(n, beta=1.8, fmin=1, fmax=20, seed=471)
    f1, f2, _ = voronoi(n, 30, seed=472)
    frac = 1 - sstep(0.0, 0.008, f2 - f1)
    bub = sstep(2.3, 2.9, fnoise(n, beta=0.3, fmin=120, fmax=n / 2, seed=473))
    streak = fnoise(n, beta=1.2, fmin=4, fmax=100, ax=1, ay=5, seed=474)
    sh = (n, n)
    c = mix(col((0.10, 0.30, 0.48), sh), col((0.55, 0.72, 0.82), sh), sstep(-1.5, 1.5, depth + 0.4 * streak))
    c = mix(c, col((0.85, 0.92, 0.96), sh), np.clip(frac * 0.9 + bub * 0.7, 0, 1))
    h = 0.3 * depth + 0.4 * frac + 0.2 * streak
    nrm = normal_from_height(h, 2.0)
    r = np.clip(0.06 + 0.08 * sstep(0, 2, streak) + 0.25 * frac, 0, 1)
    e = col((0.25, 0.6, 1.0), sh) * (0.05 + 0.25 * frac + 0.08 * sstep(0.5, 2, -depth))[..., None]
    return c, nrm, r, e


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy + 1e-9), 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


BRANCHES = [((0.5, 0.7), (0.85, 0.3)), ((0.5, 0.7), (0.15, 0.3)), ((0.5, 0.1), (0.85, 0.45)),
            ((0.5, -0.2), (0.15, -0.6)), ((0.5, 0.25), (0.85, -0.15)), ((0.15, 0.7), (0.85, -0.7)),
            ((0.5, -0.1), (0.85, -0.55)), ((0.5, 0.45), (0.15, 0.05))]


def tex_runes(n):
    """Runestone atlas: 4 columns (each 1:4), u in column = across the face, v = up the stone.
    Painted serpent band with runes (red ochre, black outline) + central motif. Emissive = rune glyphs."""
    W = n // 4
    crack, big, mid, fine = _rock_base(n, 481, cells=90)
    sh = (n, n)
    c = mix(col((0.3, 0.29, 0.275), sh), col((0.46, 0.45, 0.42), sh), sstep(-1.5, 1.5, big + 0.5 * mid))
    c *= (0.9 + 0.07 * fine)[..., None]
    c = mix(c, col((0.06, 0.055, 0.05), sh), crack * 0.6)
    ys, xs = np.mgrid[0:n, 0:n]
    lx = ((xs % W) + 0.5) / W
    LY = (ys + 0.5) / W              # 0..4 up the stone
    colid = xs // W
    x_l, x_r, y0, y1, R = 0.2, 0.8, 0.35, 3.25, 0.3
    hw = 0.075
    # band coordinates: s along path, d across (-1..1)
    s = np.zeros(sh)
    d = np.full(sh, 9.0)
    in_line = LY < y1
    dl = (lx - x_l) / hw
    dr = (lx - x_r) / hw
    use_l = in_line & (np.abs(dl) <= np.abs(dr))
    use_r = in_line & ~use_l
    d = np.where(use_l, dl, d)
    s = np.where(use_l, LY, s)
    d = np.where(use_r, -dr, d)
    arc_len = math.pi * R
    s = np.where(use_r, y1 + arc_len + (y1 - LY), s)
    rr = np.hypot(lx - 0.5, LY - y1)
    ang = np.arctan2(LY - y1, -(lx - 0.5))   # 0 at left, pi at right
    use_a = ~in_line
    d = np.where(use_a, (rr - R) / hw, d)
    s = np.where(use_a, y1 + ang * R, s)
    band = (np.abs(d) <= 1.0) & (LY > y0 - 0.02)
    outline = band & (np.abs(d) > 0.78)
    cell = 0.13
    ci = np.floor(s / cell).astype(int)
    sl = s / cell - ci
    rng = np.random.default_rng(482)
    gl = rng.integers(0, 256, size=4096)
    gtype = gl[(ci + colid * 97) % 4096]
    gx, gy = sl, d / 0.78
    glyph = np.zeros(sh, bool)
    stave = (np.abs(gx - 0.5) < 0.07) & (np.abs(gy) < 0.78)
    glyph |= stave
    for k, ((ax_, ay_), (bx_, by_)) in enumerate(BRANCHES):
        has = ((gtype >> k) & 1) == 1
        if k >= 5:
            has &= ((gtype >> (k - 5)) & 3) == 0
        dist = _seg_dist(gx, gy, ax_, ay_, bx_, by_)
        glyph |= has & (dist < 0.085)
    glyph &= band & ~outline & (sl > 0.12) & (sl < 0.88)
    # serpent head at the band start (bottom left) and tail curl (bottom right)
    red = col((0.42, 0.06, 0.03), sh)
    blk = col((0.03, 0.025, 0.02), sh)
    paint = sstep(-1.6, 0.0, fnoise(n, beta=0.9, fmin=10, fmax=300, seed=483) + 1.4)  # paint wear
    c = np.where((band & ~outline)[..., None], mix(c, red, paint * 0.95), c)
    c = np.where(outline[..., None], mix(c, blk, paint), c)
    c = np.where(glyph[..., None], mix(c, blk, paint), c)
    # central motif per column
    mx, my = lx - 0.5, LY - 1.9
    mr = np.hypot(mx, my) / 0.22
    ma = np.arctan2(my, mx) % (2 * math.pi)
    motif = np.zeros(sh, bool)
    for cid in range(4):
        m = colid == cid
        if cid == 0:
            mm = ((ma * 3 / (2 * math.pi) + mr * 2.0) % 1.0 < 0.38) & (mr > 0.15) & (mr < 1.0)
        elif cid == 1:
            mm = ((np.abs(mx) < 0.035) | (np.abs(my) < 0.035)) & (mr < 1.0) | ((mr > 0.82) & (mr < 1.0))
        elif cid == 2:
            mm = (np.abs(((ma / (2 * math.pi)) * 8 + 0.5) % 1 - 0.5) < 0.08) & (mr < 1.0) | (mr < 0.2)
        else:
            mm = ((mr % 0.34) < 0.13) & (mr < 1.0)
        motif |= m & mm
    c = np.where(motif[..., None], mix(c, blk, paint), c)
    h = 0.5 * mid + 0.12 * fine - 0.9 * crack - 0.5 * (glyph | motif) - 0.15 * outline
    nrm = normal_from_height(h, 4.0)
    r = np.clip(0.86 + 0.04 * fine - 0.12 * band * paint, 0, 1)
    e = col((0.3, 0.75, 1.0), sh) * glyph[..., None] * 0.9
    return c, nrm, r, e


def tex_waterfall(n):
    """Falling water: vertical streaks, tiles in U and V. Pan +V to flow down. RGBA BC (alpha = density)."""
    streak = fnoise(n, beta=1.0, fmin=4, fmax=n / 4, ax=1, ay=12, seed=491)
    fine = fnoise(n, beta=0.6, fmin=30, fmax=n / 2, ax=1, ay=6, seed=492)
    clump = fnoise(n, beta=1.6, fmin=2, fmax=30, ax=1, ay=3, seed=493)
    s = sstep(-0.6, 1.8, streak + 0.4 * fine + 0.3 * clump)
    sh = (n, n)
    c = mix(col((0.32, 0.45, 0.48), sh), col((0.9, 0.94, 0.95), sh), s)
    a = np.clip(0.35 + 0.65 * s, 0, 1)
    nrm = normal_from_height(streak + 0.5 * fine, 2.5)
    r = np.clip(0.05 + 0.25 * s, 0, 1)
    return c, nrm, r, a


def tex_foam(n):
    """Foam / mist card: soft puffs, tiles in U; V fades out at top and bottom. RGBA BC."""
    puff = fnoise(n, beta=1.7, fmin=2, fmax=50, seed=495)
    fine = fnoise(n, beta=0.8, fmin=20, fmax=n / 3, seed=496)
    v = (np.arange(n)[:, None] + 0.5) / n * np.ones((1, n))
    fade = sstep(0.0, 0.25, v) * sstep(1.0, 0.45, v)
    a = np.clip(sstep(-0.8, 1.6, puff + 0.35 * fine) * fade, 0, 1)
    sh = (n, n)
    c = mix(col((0.7, 0.76, 0.78), sh), col((0.95, 0.97, 0.98), sh), sstep(-1, 1.5, puff))
    nrm = normal_from_height(puff * 0.3, 1.0)
    r = np.full((n, n), 0.7)
    return c, nrm, r, a


# --------------------------------------------------------------------------- build
def build_all(bpy, outdir, hi=2048, lo=1024):
    os.makedirs(outdir, exist_ok=True)
    sets = {}

    def save(tname, n, c=None, nrm=None, r=None, e=None, alpha=None):
        d = {"size": n}
        p = lambda m: os.path.join(outdir, f"{tname}_{m}.png")  # noqa: E731
        if c is not None:
            d["BC"] = _save(bpy, f"{tname}_BC", srgb_encode(c), n, True, p("BC"), alpha=alpha)
        if nrm is not None:
            d["N"] = _save(bpy, f"{tname}_N", nrm, n, False, p("N"))
            dx = nrm.copy()
            dx[..., 1] = 1.0 - dx[..., 1]
            _save(bpy, f"{tname}_N_DX", dx, n, False, p("N_DX"))
        if r is not None:
            d["R"] = _save(bpy, f"{tname}_R", r, n, False, p("R"))
        if e is not None:
            d["E"] = _save(bpy, f"{tname}_E", srgb_encode(e), n, True, p("E"))
        sets[tname] = d
        print("TEX", tname, n)

    save("T_Shingle", hi, *tex_shingle(hi))
    c, nrm, r, crack, mid = tex_rock(lo)
    save("T_Rock", lo, c, nrm, r)
    save("T_RockFrost", lo, tex_rock_frost(lo, crack, mid))
    save("T_LavaRock", lo, *tex_lava(lo))
    save("T_Obsidian", lo, *tex_obsidian(lo))
    save("T_Crystal", 512, *tex_crystal(512))
    save("T_Bone", lo, *tex_bone(lo))
    save("T_Charred", lo, *tex_charred(lo))
    save("T_Ice", lo, *tex_ice(lo))
    save("T_Runes", hi, *tex_runes(hi))
    c, nrm, r, a = tex_waterfall(lo)
    save("T_Waterfall", lo, c, nrm, r, alpha=a)
    c, nrm, r, a = tex_foam(512)
    save("T_Foam", 512, c, nrm, r, alpha=a)
    return sets
