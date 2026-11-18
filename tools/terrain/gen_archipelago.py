"""Generate the Dragon Rider archipelago: heightmaps (16-bit PNG + raw .r16) and a JSON layout.

Run with the system Python (numpy; tifffile only for the real DEM):
  python -I tools/terrain/gen_archipelago.py [--dem <tile.tif> [<tile.tif> ...]] [--quick] [--only forest,glacier]

Output: Game/DragonRider/Saved/Generated/Archipelago/ (not in Git)
  <island>.png / <island>.r16   heightmap, Unreal Landscape encoding (see terrain_lib.to_uint16)
  <island>_preview.png          hillshaded preview
  archipelago.json              world placement, landscape scale, points of interest (metres, Unreal axes)

Islands
  main     the fjord island. Real elevation when DEM tiles are given (Copernicus GLO-30, Fjaerlandsfjorden,
           Sognefjord, Norway), otherwise a procedural fjord island placeholder.
  forest   rolling, wooded; a big east-coast cliff with a waterfall gorge.
  glacier  tall jagged peaks, ice fields, a steep fjord-cut coast.
  ember    volcanic cone with a caldera (lava lake), black-sand beaches, lava-rock flows: the dragon's lair.
  skerry_* small rock skerries and sea stacks in the channels between the islands.

Axes: column = +X, row = +Y (Unreal world). Sea level = 0 m. Every island is eroded with the stream power law
(dendritic valleys, sharp ridges) at ~5 m cells, then upsampled with thermal talus, coastal cliffs/beaches and
fine detail at full resolution.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terrain_lib as tl  # noqa: E402
from png16 import write_png  # noqa: E402

PROJECT = os.path.normpath(os.path.join(HERE, '..', '..', 'Game', 'DragonRider'))
OUT = os.path.join(PROJECT, 'Saved', 'Generated', 'Archipelago')
DEM_DIR = os.path.join(PROJECT, 'Saved', 'Generated', 'DEM')
DEM_DEFAULT = [os.path.join(DEM_DIR, 'Copernicus_DSM_COG_10_N61_00_E006_00_DEM.tif'),
               os.path.join(DEM_DIR, 'Copernicus_DSM_COG_10_N61_00_E007_00_DEM.tif')]
# Main island DEM window: Fjaerlandsfjorden (a Sognefjord arm). The fjord enters from the south and ends at the
# Fjaerland valley inside the island; the window's edges are drowned into a ria coast.
DEM_CENTRE = (6.73, 61.39)   # lon E, lat N
DEM_SIZE_M = 14112.0         # 4033 px at 3.5 m
DEM_EXAGGERATE = 1.1

T0 = time.time()


def log(msg):
    print('[%6.1fs] %s' % (time.time() - T0, msg), flush=True)


# Landscape-friendly sizes: (n - 1) must be a multiple of 126 (components of 2x2 sections of 63 quads).
ISLANDS = {
    #          px    m/px  world centre (m)       erosion grid
    'main':    (4033, 3.5, (0.0, 0.0),            1009),
    'forest':  (2521, 2.0, (11700.0, -2600.0),    1009),
    'glacier': (3025, 2.0, (1500.0, -11800.0),    1009),
    'ember':   (2521, 2.0, (10800.0, 10400.0),    1009),
}
SKERRIES = {
    # name: (px, m/px, centre) - small 1 km tiles in the channels
    'skerry_east':  (505, 2.0, (7900.0, -5600.0)),
    'skerry_north': (505, 2.0, (7400.0, -9600.0)),
    'skerry_south': (505, 2.0, (5600.0, 8600.0)),
}


# ---------------------------------------------------------------------------------------------------------- helpers
def island_mask(X, Y, nz, rx, ry, rot_deg, warp=0.35, seed_off=0.0):
    """Soft island footprint: a rotated ellipse with a domain-warped (fractal) outline. 1 inside, <0 outside."""
    a = math.radians(rot_deg)
    xr = X * math.cos(a) + Y * math.sin(a)
    yr = -X * math.sin(a) + Y * math.cos(a)
    wx = tl.fbm(nz, X / 1800.0 + seed_off, Y / 1800.0, 5) * warp
    wy = tl.fbm(nz, X / 1800.0 - 40.0, Y / 1800.0 + seed_off, 5) * warp
    r = np.sqrt((xr / rx + wx) ** 2 + (yr / ry + wy) ** 2)
    return 1.0 - r


def erode(intent, size_m, n_hi, k=2e-5, iters=(120, 40), umax=8e-4, rain=None, talus=33.0, log_tag='', diffusion=0.05):
    """Steady-state stream power on two grids (coarse then fine), driven by `intent` (0 at the coast, 1 = highest
    uplift; < 0 = sea, kept at its depth). Returns eroded height (m, unscaled) and log drainage area at n_hi."""
    out, A = None, None
    for stage, (n, its) in enumerate(((n_hi // 2 + 1, iters[0]), (n_hi, iters[1]))):
        it_in = tl.resize(intent, n)
        dx = size_m / (n - 1)
        sea = it_in <= 0.0
        if out is None:
            # initial surface: the intent plus noise, so drainage doesn't start on a perfectly smooth (D8-biased) slope
            Xn, Yn = tl.grid(n, size_m)
            jit = tl.fbm(tl.Perlin(77), Xn / 180.0, Yn / 180.0, 4) * 4.0 + np.random.default_rng(7).random((n, n)) * 0.5
            h0 = np.where(sea, it_in * 60.0, it_in * 30.0 + jit)
        else:
            h0 = tl.resize(out, n)
            h0 = np.where(sea, it_in * 60.0, np.maximum(h0, 0.05))
        U = np.where(sea, 0.0, umax * np.clip(it_in, 0.0, None) ** 0.8)
        rn = None if rain is None else tl.resize(rain, n)
        log('%s erosion stage %d: %dx%d, %d iterations' % (log_tag, stage + 1, n, n, its))
        out, A = tl.stream_power(h0, sea, dx, U, its, k=k, dt=2500.0, rain=rn, log=log, seed=stage + 3, diffusion=diffusion)
        out = tl.thermal(out, dx, talus, 6, mask=~sea)
    return out, A


def drown(h, metres):
    """Raise the sea: low valley mouths flood into coves and inlets (a ria coast), headlands stay."""
    return np.where(h > 0, h - metres, h - metres * 0.5)


def finish(h_lo, n, size_m, nz, detail_m=3.0, talus=38.0, thermal_iters=10, rock_noise=1.0):
    """Upsample to the landscape grid and add the sub-5 m detail: rock crags on steep ground, soil on flats."""
    h = tl.resize(h_lo, n)
    dx = size_m / (n - 1)
    X, Y = tl.grid(n, size_m)
    s = tl.slope(h, dx)
    steep = tl.smoothstep(0.35, 1.1, s)
    crag = (tl.ridged(nz, X / 90.0, Y / 90.0, 4) - 0.45) * detail_m * 2.2 * rock_noise
    soil = tl.fbm(nz, X / 40.0 + 3.1, Y / 40.0, 3) * detail_m * 0.35
    land = h > 0.5
    h = h + np.where(land, steep * crag + (1 - steep) * soil, 0.0) * tl.smoothstep(0.5, 8.0, h)
    h = tl.thermal(h, dx, talus, thermal_iters, mask=land)
    return h, X, Y


def coast(h, X, Y, dx, nz, cliff_h=40.0, cliff_bias=0.0, beach_bias=0.0, shelf=55.0, shelf_len=160.0,
          beach_w=70.0, cliff_mask=None):
    """Coastal shaping on the full-res grid: wave-cut cliffs on exposed shores, beaches in low sheltered bays,
    and a smooth sloping sea floor."""
    sea = h <= 0.0
    # distance inland from the shore / out to sea (blurred a little: the chamfer sweep leaves faint streaks)
    d_land = np.where(sea, 0.0, tl.blur(tl.distance_field(sea, dx), 2.0))
    d_sea = np.where(sea, tl.blur(tl.distance_field(~sea, dx), 2.0), 0.0)
    expo = tl.fbm(nz, X / 2200.0 + 11.0, Y / 2200.0 - 5.0, 3) * 1.6 + cliff_bias
    if cliff_mask is not None:
        expo = np.maximum(expo, cliff_mask * 2.0)
    cliff = tl.smoothstep(0.05, 0.45, expo)
    # Cliff: land within ~25 m of the shore is raised into a near-vertical wall of height cliff_h (scaled down
    # where the land behind is already low, so the cliff top meets the slope).
    rise = cliff_h * (1.0 - np.exp(-d_land / 9.0)) * tl.smoothstep(0.0, 60.0, d_land + 40.0)
    fade = 1.0 - tl.smoothstep(60.0, 260.0, d_land)
    h = np.where(sea, h, h + cliff * rise * fade * tl.smoothstep(-0.2, 0.6, 1.0 - h / (cliff_h * 3.0)))
    # Beach: in sheltered, low ground the first beach_w metres are flattened to a gentle 2-6 % slope.
    beach = tl.smoothstep(0.1, 0.6, -expo + beach_bias) * (1.0 - tl.smoothstep(15.0, 45.0, h))
    target = d_land * (0.03 + 0.03 * tl.fbm(nz, X / 300.0, Y / 300.0, 2))
    bw = beach * (1.0 - tl.smoothstep(beach_w * 0.6, beach_w * 1.6, d_land))
    h = np.where(sea, h, h * (1 - bw) + np.minimum(h, target + 0.4) * bw)
    # Sea floor: steeper under cliffs, gentle shelf off beaches.
    depth = shelf * (1.0 - np.exp(-d_sea / (shelf_len * (0.45 + 0.55 * (1 - cliff))))) + 0.6
    h = np.where(sea, np.minimum(h, -depth), h)
    return h, cliff, beach


def rain_field(X, Y, nz, wet_dir=(-1.0, 0.3)):
    """Orographic-ish rain: wetter on the windward side, noisy. Drives the drainage area weighting."""
    w = (X * wet_dir[0] + Y * wet_dir[1]) / (np.abs(X).max() + 1)
    return np.clip(1.0 + 0.5 * w + 0.3 * tl.fbm(nz, X / 3000.0, Y / 3000.0, 3), 0.3, 2.0)


def pick_site(h, X, Y, dx, want, avoid=(), min_sep=600.0, prefer=None):
    """Best flat, low site next to deep water (village / harbour). Returns (x, y, z) metres in island space."""
    sea = h <= 0
    s = tl.slope(h, dx)
    d_land = tl.distance_field(sea, dx)
    deep = tl.distance_field(h < -6.0, dx)
    flat = tl.blur(s, 30.0 / dx)
    score = flat * 6.0 + np.abs(d_land - want.get('shore', 120.0)) / 200.0 + deep / 400.0
    score = score + np.where((h > want.get('zmin', 3.0)) & (h < want.get('zmax', 30.0)), 0.0, 99.0)
    if prefer is not None:
        px, py, w = prefer
        score = score + np.hypot(X - px, Y - py) / w
    for ax, ay in avoid:
        score = score + np.where(np.hypot(X - ax, Y - ay) < min_sep, 99.0, 0.0)
    i = int(np.argmin(score))
    r, c = divmod(i, h.shape[1])
    return float(X[r, c]), float(Y[r, c]), float(h[r, c])


# ---------------------------------------------------------------------------------------------------------- recipes
def recipe_forest(n, dx, n_ero, quick):
    """Rolling wooded isle. Big east cliff; a river gorge cuts the cliff and ends in a waterfall."""
    size = dx * (n - 1)
    nz = tl.Perlin(101)
    Xe, Ye = tl.grid(n_ero, size)
    m = island_mask(Xe, Ye, nz, 2050.0, 1650.0, 18.0, warp=0.28)
    # Plateau that ends abruptly in the east: the east side keeps its height right to the coast.
    hills = 0.55 + 0.45 * tl.fbm(nz, Xe / 1400.0, Ye / 1400.0, 5)
    east = tl.smoothstep(-300.0, 1500.0, Xe)
    intent = np.where(m > 0, np.clip(m * 2.2, 0, 1) ** 0.7 * hills * (0.75 + 0.35 * east), m * 1.5)
    h, _ = erode(intent, size, n_ero, k=2.0e-4, iters=(40, 12) if quick else (110, 36), umax=6e-4,
                 rain=rain_field(Xe, Ye, nz), talus=26.0, log_tag='forest', diffusion=0.018)
    h = np.where(h > 0, h / max(h.max(), 1.0) * 380.0, h)
    h = drown(h, 14.0)
    h, X, Y = finish(h, n, size, nz, detail_m=2.0, talus=34.0, rock_noise=0.6)

    # Waterfall gorge: a winding V-gorge from the interior to the east cliff, floor dropping 0.6 %,
    # ending in a 2-step lip ~90 m above the sea.
    cliff_mask = tl.smoothstep(600.0, 1400.0, X * 0.94 + Y * 0.34) * 1.0
    h, cliff, beach = coast(h, X, Y, dx, nz, cliff_h=95.0, cliff_bias=-0.25, beach_bias=0.4, cliff_mask=cliff_mask)
    sea = h <= 0
    # find the gorge exit: the cliff-top point on the east shore nearest the bearing from the centre
    d_land = tl.distance_field(sea, dx)
    ang = np.arctan2(Y, X)
    cand = (d_land > 40.0) & (d_land < 60.0) & (np.abs(ang - math.radians(8.0)) < 0.12) & (h > 60.0)
    if not cand.any():
        cand = (d_land > 40.0) & (d_land < 60.0) & (X > 0) & (h > 40.0)
    idx = np.flatnonzero(cand)
    lip = idx[np.argmax(X.ravel()[idx])]
    lx, ly = float(X.ravel()[lip]), float(Y.ravel()[lip])
    lip_z = float(h.ravel()[lip])
    # gorge path: from the lip back inland (west-north-west), gently meandering
    t = np.linspace(0, 1, 400)
    length = 1700.0
    px = lx - t * length * 0.95
    py = ly - t * length * 0.25 + 120.0 * np.sin(t * 7.0) * t
    floor = lip_z - 22.0 + t * length * 0.012
    # distance from every cell to the path (min over samples, in chunks), and the floor height there
    gd, gz = _path_distance(X, Y, px, py, floor, width_hint=180.0)
    depth_cut = np.clip(h - gz, 0.0, None)
    v = 1.0 - tl.smoothstep(10.0, 18.0 + 0.9 * depth_cut, gd)      # V-profile: wider where the cut is deeper
    h = np.where(sea, h, h - depth_cut * v)
    # Plunge pool below the falls: a small cove carved into the cliff foot.
    pool = 1.0 - tl.smoothstep(25.0, 70.0, np.hypot(X - (lx + 55.0), Y - (ly + 15.0)))
    h = np.where(pool > 0, h * (1 - pool) + (-6.0) * pool, h)
    wf = (lx, ly, float(lip_z - 22.0))

    village = pick_site(h, X, Y, dx, dict(shore=110.0, zmin=3.0, zmax=22.0), prefer=(-1500.0, 600.0, 1500.0))
    pois = dict(waterfall=dict(x=wf[0], y=wf[1], z=wf[2], top_z=wf[2], base_z=0.0, dir_deg=float(math.degrees(math.atan2(0.25, 0.95)))),
                village=dict(x=village[0], y=village[1], z=village[2], name='Lundvik'))
    return h, pois, dict(snow_line=99999.0, kind='forest')


def _path_distance(X, Y, px, py, pz, width_hint):
    """Distance (m) from each cell to a sampled polyline, and the polyline's z at the nearest sample.
    Only cells inside the path's bounding box (+width) are evaluated."""
    gd = np.full(X.shape, 1e9)
    gz = np.zeros(X.shape)
    pad = width_hint * 2
    x0, x1, y0, y1 = px.min() - pad, px.max() + pad, py.min() - pad, py.max() + pad
    xs, ys = X[0], Y[:, 0]
    c0, c1 = np.searchsorted(xs, x0), np.searchsorted(xs, x1)
    r0, r1 = np.searchsorted(ys, y0), np.searchsorted(ys, y1)
    sx, sy = X[r0:r1, c0:c1], Y[r0:r1, c0:c1]
    bd = np.full(sx.shape, 1e9); bz = np.zeros(sx.shape)
    for k in range(len(px)):
        d = np.hypot(sx - px[k], sy - py[k])
        better = d < bd
        bd = np.where(better, d, bd); bz = np.where(better, pz[k], bz)
    gd[r0:r1, c0:c1] = bd; gz[r0:r1, c0:c1] = bz
    return gd, gz


def recipe_glacier(n, dx, n_ero, quick):
    """Tall jagged peaks, smooth ice fields in the high cirques, a coast cut by steep fjords.
    Fjords are made the way real ones are: the big river valleys of the eroded range are over-deepened into
    U-shaped glacial troughs (depth ~ sqrt(drainage area), blurred across the valley) and then drowned by the sea."""
    size = dx * (n - 1)
    nz = tl.Perlin(202)
    Xe, Ye = tl.grid(n_ero, size)
    m = island_mask(Xe, Ye, nz, 2650.0, 2050.0, -24.0, warp=0.42, seed_off=5.0)
    peaks = tl.ridged(nz, Xe / 1700.0, Ye / 1700.0, 6, sharp=2.4)
    core = np.clip(m * 1.6, 0, 1)
    intent = np.where(m > 0, core ** 0.55 * (0.3 + 1.0 * peaks), m * 1.5)
    h, A = erode(intent, size, n_ero, k=1.5e-4, iters=(40, 12) if quick else (130, 40), umax=9e-4,
                 rain=rain_field(Xe, Ye, nz, (0.8, -0.4)), talus=42.0, log_tag='glacier', diffusion=0.012)
    h = np.where(h > 0, h / max(h.max(), 1.0) * 1500.0, h)
    dxe = size / (n_ero - 1)
    land = h > 0
    flow = np.sqrt(np.where(land, A, 0.0) / max(float(A[land].max()), 1.0))
    trough = tl.blur(flow, 70.0 / dxe)                                    # ~150 m wide U-troughs
    trough = trough / max(float(trough.max()), 1e-6)
    h = np.where(land, h - 420.0 * tl.smoothstep(0.2, 0.75, trough) - 60.0 * trough, h)  # only the trunk valleys drown
    h = drown(h, 6.0)
    h = np.maximum(h, -160.0)
    h, X, Y = finish(h, n, size, nz, detail_m=6.0, talus=46.0, rock_noise=1.6)
    # Ice fields: high, gently sloping ground is smoothed into glacier surfaces.
    s = tl.slope(h, dx)
    ice = tl.smoothstep(700.0, 950.0, h) * (1.0 - tl.smoothstep(0.35, 0.75, s))
    h = h * (1 - ice) + tl.blur(h, 18.0) * ice
    h, cliff, beach = coast(h, X, Y, dx, nz, cliff_h=35.0, cliff_bias=0.5, beach_bias=-0.4, shelf=110.0, shelf_len=120.0)
    peak = np.unravel_index(int(np.argmax(h)), h.shape)
    pois = dict(summit=dict(x=float(X[peak]), y=float(Y[peak]), z=float(h[peak])))
    return h, pois, dict(snow_line=560.0, kind='glacier')


def recipe_ember(n, dx, n_ero, quick):
    """Volcanic cone with a caldera and lava lake, radial gullies, lava-rock flows to black-sand beaches."""
    size = dx * (n - 1)
    nz = tl.Perlin(303)
    Xe, Ye = tl.grid(n_ero, size)
    m = island_mask(Xe, Ye, nz, 2150.0, 1950.0, 40.0, warp=0.18, seed_off=9.0)
    r = np.hypot(Xe - 150.0, Ye + 100.0)
    cone = np.clip(1.0 - r / 2100.0, 0, 1) ** 1.25
    flank = 0.08 * tl.fbm(nz, Xe / 900.0, Ye / 900.0, 4)
    intent = np.where(m > 0, np.clip(m * 3.0, 0, 1) * (0.12 + cone + flank), m * 1.5)
    h, _ = erode(intent, size, n_ero, k=1.2e-4, iters=(40, 10) if quick else (90, 26), umax=7e-4,
                 talus=34.0, log_tag='ember')
    h = np.where(h > 0, h / max(h.max(), 1.0) * 1180.0, h)
    # Keep the cone's clean profile: blend the eroded relief with the ideal cone (gullies stay, lumps go).
    ideal = np.where(m > 0, np.clip(m * 3.0, 0, 1) * (0.12 + cone) / 1.12 * 1180.0, h)
    h = np.where(h > 0, 0.55 * h + 0.45 * ideal, h)
    h, X, Y = finish(h, n, size, nz, detail_m=3.5, talus=36.0, rock_noise=1.2)
    cx, cy = 150.0, -100.0
    r = np.hypot(X - cx, Y - cy)
    # Lava flows: rough lobes 8-14 m thick running downhill from the rim to the sea on three sides.
    for k, (ang, width) in enumerate(((math.radians(-35), 120.0), (math.radians(150), 95.0), (math.radians(80), 80.0))):
        t = np.linspace(0, 1, 300)
        rr = 450.0 + t * 2200.0
        aa = ang + 0.25 * np.sin(t * 5.0 + k)
        px, py = cx + rr * np.cos(aa), cy + rr * np.sin(aa)
        d, _ = _path_distance(X, Y, px, py, t, width * 1.5)
        lobe = 1.0 - tl.smoothstep(width * 0.55, width, d + 25.0 * tl.fbm(nz, X / 60.0 + k, Y / 60.0, 3))
        thick = 10.0 + 4.0 * tl.ridged(nz, X / 35.0, Y / 35.0, 3)
        h = np.where(h > -2.0, h + lobe * thick, h)
    # Caldera: steep inner walls, a flat floor with a lava lake ~260 m below the rim.
    rim_r, floor_r = 520.0, 330.0
    rim_z = float(np.percentile(h[(r > rim_r - 40) & (r < rim_r + 40)], 60))
    floor_z = rim_z - 260.0
    bowl = floor_z + (rim_z - floor_z) * tl.smoothstep(floor_r, rim_r, r) ** 1.6
    h = np.where(r < rim_r + 60.0, np.minimum(h, bowl + 8.0 * tl.fbm(nz, X / 50.0, Y / 50.0, 3)), h)
    rim = np.exp(-((r - rim_r) / 60.0) ** 2) * 35.0
    h = h + rim * (h > 0)
    h, cliff, beach = coast(h, X, Y, dx, nz, cliff_h=18.0, cliff_bias=-0.6, beach_bias=0.9, shelf=80.0, shelf_len=220.0,
                            beach_w=90.0)
    pois = dict(caldera=dict(x=cx, y=cy, z=floor_z, rim_z=rim_z, radius=rim_r, lava_radius=floor_r))
    return h, pois, dict(snow_line=99999.0, kind='ember')


def recipe_skerry(n, dx, seed):
    """A cluster of low rock skerries and a few tall sea stacks."""
    size = dx * (n - 1)
    nz = tl.Perlin(seed)
    X, Y = tl.grid(n, size)
    rng = np.random.default_rng(seed)
    h = np.full(X.shape, -30.0) + 18.0 * tl.fbm(nz, X / 250.0, Y / 250.0, 4)
    stacks = []
    for i in range(rng.integers(5, 8)):
        sx, sy = rng.uniform(-330, 330, 2)
        tall = i < 3
        rad = rng.uniform(14, 26) if tall else rng.uniform(35, 90)
        top = rng.uniform(28, 55) if tall else rng.uniform(3, 9)
        rr = np.hypot(X - sx, Y - sy) + 10.0 * tl.fbm(nz, X / 40.0 + i, Y / 40.0, 3)
        prof = top * (1.0 - tl.smoothstep(rad * (0.75 if tall else 0.2), rad, rr)) ** (0.4 if tall else 1.5)
        prof = prof + (tl.ridged(nz, X / 25.0 + i, Y / 25.0, 3) - 0.5) * (6.0 if tall else 2.0) * (prof > 1)
        base = -30.0 + 27.0 * (1.0 - tl.smoothstep(rad, rad * 2.6, rr))   # submerged apron
        rock = np.where(prof > 0.3, prof, -99.0)   # the stack itself, only where it stands above water
        h = np.maximum(h, np.maximum(rock, base))
        if tall:
            stacks.append(dict(x=float(sx), y=float(sy), z=float(top)))
    h = tl.thermal(h, dx, 60.0, 4)
    return h, dict(stacks=stacks), dict(snow_line=99999.0, kind='skerry')


def recipe_main_procedural(n, dx, n_ero, quick):
    """Placeholder main island when no DEM tiles are available: a fjord island with steep ridges."""
    size = dx * (n - 1)
    nz = tl.Perlin(404)
    Xe, Ye = tl.grid(n_ero, size)
    m = island_mask(Xe, Ye, nz, 6000.0, 5600.0, 0.0, warp=0.25)
    peaks = tl.ridged(nz, Xe / 3200.0, Ye / 3200.0, 6)
    intent = np.where(m > 0, np.clip(m * 2.0, 0, 1) ** 0.6 * (0.3 + peaks), m * 1.5)
    t = np.linspace(0, 1, 300)
    px = 600.0 * np.sin(t * 5.0); py = 7000.0 - t * 7600.0
    d, _ = _path_distance(Xe, Ye, px, py, t, 600.0)
    cut = 1.0 - tl.smoothstep(250.0, 700.0, d)
    intent = intent * (1 - cut) - 0.6 * cut
    h, _ = erode(intent, size, n_ero, k=1.5e-4, iters=(40, 10) if quick else (120, 30), umax=9e-4, log_tag='main')
    h = np.where(h > 0, h / max(h.max(), 1.0) * 1500.0, h)
    h, X, Y = finish(h, n, size, nz, detail_m=4.0, talus=42.0)
    h, _, _ = coast(h, X, Y, dx, nz, cliff_h=25.0)
    return h, X, Y, dict(source='procedural placeholder')


def recipe_main_dem(n, dx, n_ero, quick, dem_paths):
    """Main island from the real DEM, with a light erosion pass to add the gullies and crags below 30 m."""
    import dem_import
    size = dx * (n - 1)
    h, info = dem_import.build_dem_island(dem_paths, DEM_CENTRE[0], DEM_CENTRE[1], size, n,
                                          exaggerate=DEM_EXAGGERATE, log=log)
    # Light erosion at ~7 m: short stream power run (no uplift) carves gullies into the smooth upsampled DEM.
    n_mid = 2017 if not quick else 1009
    hm = tl.resize(h, n_mid, cubic=False)
    dxm = size / (n_mid - 1)
    sea = hm <= 0.0
    log('main: light erosion at %dx%d (%.1f m cells)' % (n_mid, n_mid, dxm))
    he, _ = tl.stream_power(hm, sea, dxm, np.zeros_like(hm), 3 if quick else 8, k=4e-6, dt=2500.0, refill_every=100, log=log)
    he = tl.thermal(he, dxm, 40.0, 6, mask=~sea)
    diff = tl.resize(he - hm, n, cubic=False)
    h = np.where(h > 0, np.maximum(h + diff, 0.3), h)
    nz = tl.Perlin(505)
    X, Y = tl.grid(n, size)
    s = tl.slope(h, dx)
    steep = tl.smoothstep(0.4, 1.2, s)
    crag = (tl.ridged(nz, X / 110.0, Y / 110.0, 4) - 0.45) * 9.0
    h = np.where(h > 1.0, h + steep * crag * tl.smoothstep(1.0, 20.0, h), h)
    h = tl.thermal(h, dx, 42.0, 6, mask=h > 0)
    info.update(source='Copernicus GLO-30', lon=DEM_CENTRE[0], lat=DEM_CENTRE[1], size_m=size, exaggerate=DEM_EXAGGERATE)
    return h, X, Y, info


# ---------------------------------------------------------------------------------------------------------- main
def save_island(name, h, px, dx, centre, pois, extra, layout):
    zs = tl.z_scale_for(h)
    v = tl.to_uint16(h, zs)
    write_png(os.path.join(OUT, name + '.png'), v)
    v.astype('<u2').tofile(os.path.join(OUT, name + '.r16'))
    small = max(1, px // 1024)
    write_png(os.path.join(OUT, name + '_preview.png'), tl.preview_rgb(h[::small, ::small], dx * small))
    size = dx * (px - 1)
    # POIs to world space
    wp = {}
    for k, p in pois.items():
        if isinstance(p, dict) and 'x' in p:
            q = dict(p); q['x'] = p['x'] + centre[0]; q['y'] = p['y'] + centre[1]; wp[k] = q
        elif isinstance(p, list):
            wp[k] = [dict(q, x=q['x'] + centre[0], y=q['y'] + centre[1]) for q in p]
    layout['islands'][name] = dict(
        heightmap=name + '.r16', png=name + '.png', size_px=px, m_per_px=dx, size_m=size,
        centre=[centre[0], centre[1]], z_scale=zs,
        # Unreal actor transform: location of vertex (0, 0) and scale (cm)
        landscape_location_cm=[(centre[0] - size / 2) * 100.0, (centre[1] - size / 2) * 100.0, 0.0],
        landscape_scale=[dx * 100.0, dx * 100.0, zs],
        min_m=float(h.min()), max_m=float(h.max()), land_fraction=float((h > 0).mean()),
        pois=wp, **extra)
    log('%s: %dx%d @ %.1f m, %.0f..%.0f m, land %.0f%%, z scale %.1f' % (
        name, px, px, dx, h.min(), h.max(), 100 * (h > 0).mean(), zs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dem', nargs='*', default=None, help='GeoTIFF DEM tiles for the main island (default: Saved/Generated/DEM)')
    ap.add_argument('--no-dem', action='store_true', help='use the procedural main island placeholder')
    ap.add_argument('--quick', action='store_true', help='fewer erosion iterations (fast preview)')
    ap.add_argument('--only', default='', help='comma list of islands to (re)build; others are kept from the last run')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    lp = os.path.join(OUT, 'archipelago.json')
    layout = json.load(open(lp)) if (a.only and os.path.exists(lp)) else dict(islands={})
    only = set(a.only.split(',')) if a.only else None
    layout.update(sea_level_m=0.0, axes='col=+X row=+Y, metres; Unreal cm = m*100', generator='tools/terrain/gen_archipelago.py')

    for name, (px, dx, centre, n_ero) in ISLANDS.items():
        if only and name not in only:
            continue
        t = time.time()
        if name == 'main':
            dem = a.dem if a.dem else ([] if a.no_dem else [p for p in DEM_DEFAULT if os.path.exists(p)])
            if dem:
                h, X, Y, info = recipe_main_dem(px, dx, n_ero, a.quick, dem)
            else:
                h, X, Y, info = recipe_main_procedural(px, dx, n_ero, a.quick)
            pois = {}
            # Main village: a flat harbour site at the fjord head / a sheltered shore. Start point: out at sea,
            # south of the fjord mouth, looking up the fjord.
            v = pick_site(h, X, Y, dx, dict(shore=140.0, zmin=3.0, zmax=25.0), prefer=(0.0, -4000.0, 2500.0))
            pois['village'] = dict(x=v[0], y=v[1], z=v[2], name='Fjaerholm')
            v2 = pick_site(h, X, Y, dx, dict(shore=140.0, zmin=3.0, zmax=25.0), avoid=[(v[0], v[1])], min_sep=3000.0,
                           prefer=(0.0, 3500.0, 2500.0))
            pois['village_b'] = dict(x=v2[0], y=v2[1], z=v2[2], name='Sognvik')
            mouth = _fjord_mouth(h, X, Y, dx)
            pois['fjord_mouth'] = dict(x=mouth[0], y=mouth[1], z=0.0)
            extra = dict(snow_line=1150.0, kind='main', source=info)
            del X, Y
        elif name == 'forest':
            h, pois, extra = recipe_forest(px, dx, n_ero, a.quick)
        elif name == 'glacier':
            h, pois, extra = recipe_glacier(px, dx, n_ero, a.quick)
        else:
            h, pois, extra = recipe_ember(px, dx, n_ero, a.quick)
        save_island(name, h, px, dx, centre, pois, extra, layout)
        log('%s done in %.0f s' % (name, time.time() - t))
        del h
    for k, (name, (px, dx, centre)) in enumerate(SKERRIES.items()):
        if only and name not in only:
            continue
        h, pois, extra = recipe_skerry(px, dx, 900 + k)
        save_island(name, h, px, dx, centre, pois, extra, layout)

    _layout_extras(layout)
    json.dump(layout, open(lp, 'w'), indent=1)
    log('wrote %s' % lp)


def _fjord_mouth(h, X, Y, dx):
    """Where the main fjord meets the open sea. The fjord is the column (|x| < 3 km) that is sea over most of the
    island's middle rows; the mouth is the southernmost row where that column still has land within 1.5 km on
    both sides."""
    n = h.shape[0]
    xs = X[0]
    cols = np.flatnonzero(np.abs(xs) < 3000.0)
    mid = slice(int(n * 0.3), int(n * 0.7))
    sea_frac = (h[mid][:, cols] <= 0).mean(axis=0)
    c = int(cols[np.argmax(sea_frac)])
    w = int(1500.0 / dx)
    mouth_r = None
    for r in range(int(n * 0.3), n):
        if h[r, c] > 0:
            # re-centre on the channel if it wanders
            row = h[r, max(0, c - w):c + w]
            if (row <= 0).any():
                c = max(0, c - w) + int(np.flatnonzero(row <= 0)[np.argmin(np.abs(np.flatnonzero(row <= 0) - w))])
            else:
                continue
        left = (h[r, max(0, c - w):c] > 0).any()
        right = (h[r, c + 1:c + w] > 0).any()
        if left and right:
            mouth_r = r
        elif mouth_r is not None and r - mouth_r > int(400.0 / dx):
            break
    if mouth_r is None:
        return 0.0, float(Y.max() * 0.8)
    return float(X[mouth_r, c]), float(Y[mouth_r, c])


def _layout_extras(layout):
    """Dragon start, fleet routes and review camera points derived from the islands."""
    I = layout['islands']
    if 'main' not in I:
        return
    main = I['main']
    mouth = main['pois'].get('fjord_mouth', dict(x=0.0, y=6000.0))
    # Start: 2.2 km out to sea beyond the fjord mouth, 300 m up, looking north up the fjord.
    start = dict(x=mouth['x'], y=mouth['y'] + 2600.0, z=300.0, yaw=-90.0)
    layout['start'] = start
    routes = []
    def c(nm):
        return I[nm]['centre'] if nm in I else None
    for a, b, n_ships in (('main', 'forest', 3), ('ember', 'main', 3), ('glacier', 'forest', 2)):
        if c(a) and c(b):
            routes.append(dict(src=a, dst=b, ships=n_ships))
    layout['fleet_routes'] = routes


if __name__ == '__main__':
    main()
