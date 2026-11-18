"""Pick sites for Vertex's island landmark kit on the generated archipelago heightmaps.

Run with the system Python (numpy), after gen_archipelago.py:
  python -I tools/terrain/pick_landmark_sites.py
Writes Saved/Generated/Archipelago/landmarks.json (world metres, Unreal axes), read by tools/place_landmarks.py.

Sites:
  forest   stronghold (ring-fort + mead hall + gatehouse) on the flattest ground near Lundvik, gate facing the sea;
           waterfall pieces along the marked gorge lip (archipelago.json "waterfall" POI).
  glacier  rune circle on a flat shoulder below the ice, ice shrine on the ice field above it.
  ember    dragon lair on the caldera floor, between the lava lake and the crater wall.
  all      shipwreck halves and driftwood on beaches, signal-fire (beacon) towers on low headlands.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terrain_lib as tl  # noqa: E402

GEN = os.path.normpath(os.path.join(HERE, '..', '..', 'Game', 'DragonRider', 'Saved', 'Generated', 'Archipelago'))
LAYOUT = json.load(open(os.path.join(GEN, 'archipelago.json')))


def load(name, step_m=4.0):
    """Heightmap of one island, downsampled to ~step_m (metres), with its world X/Y grids."""
    isl = LAYOUT['islands'][name]
    n = isl['size_px']
    h = (np.fromfile(os.path.join(GEN, isl['heightmap']), '<u2').reshape(n, n).astype(np.float64) - 32768.0) * isl['z_scale'] / 12800.0
    k = max(1, int(round(step_m / isl['m_per_px'])))
    h = h[::k, ::k]
    dx = isl['m_per_px'] * k
    m = h.shape[0]
    c = (np.arange(m) * dx) - isl['size_m'] / 2.0
    X, Y = np.meshgrid(c + isl['centre'][0], c + isl['centre'][1], indexing='xy')
    return h, X, Y, dx


def local_range(h, r_cells):
    """Max - min of h over a (2r+1)^2 window (separable running max/min)."""
    def run(a, fn):
        out = a.copy()
        for axis in (0, 1):
            acc = out.copy()
            for s in range(1, r_cells + 1):
                acc = fn(acc, np.roll(out, s, axis))
                acc = fn(acc, np.roll(out, -s, axis))
            out = acc
        return out
    return run(h, np.maximum) - run(h, np.minimum)


def best(score):
    i = int(np.nanargmin(score))
    return divmod(i, score.shape[1])


def sea_bearing(h, X, Y, r, c, dx):
    """Bearing (deg) from a cell toward the nearest open sea, from the lowest mean height along 24 directions."""
    lows = []
    for k in range(24):
        a = math.radians(k * 15)
        tot = 0.0
        for d in (150.0, 300.0, 500.0):
            rr = int(round(r + math.sin(a) * d / dx)); cc = int(round(c + math.cos(a) * d / dx))
            rr = min(max(rr, 0), h.shape[0] - 1); cc = min(max(cc, 0), h.shape[1] - 1)
            tot += h[rr, cc]
        lows.append((tot, k * 15.0))
    return min(lows)[1]


out = {}

# ---------------------------------------------------------------- forest: stronghold + waterfall
h, X, Y, dx = load('forest')
fp = LAYOUT['islands']['forest']['pois']
vil = fp['village']
rng_fort = local_range(h, int(40 / dx))       # whole ring-fort
d_vil = np.hypot(X - vil['x'], Y - vil['y'])
sea = h <= 0
d_sea = tl.distance_field(sea, dx)
score = rng_fort + np.abs(d_vil - 700.0) / 400.0
score[(h < 6) | (h > 200) | (d_vil < 350) | (d_sea < 70)] = np.nan


def hall_range(r, c, yaw):
    """Height range under the mead hall's 52 x 18 m footprint at a yaw (deg)."""
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    hs = []
    for u in np.linspace(-26, 26, 9):
        for v in np.linspace(-9, 9, 4):
            rr = int(round(r + (u * sa + v * ca) / dx)); cc = int(round(c + (u * ca - v * sa) / dx))
            hs.append(h[min(max(rr, 0), h.shape[0] - 1), min(max(cc, 0), h.shape[1] - 1)])
    return max(hs) - min(hs)


cands = np.argsort(np.where(np.isnan(score), np.inf, score).ravel())[:400]
best_site = None
for i in cands:
    r, c = divmod(int(i), score.shape[1])
    hr, yaw = min((hall_range(r, c, y), y) for y in range(0, 180, 15))
    tot = hr * 2.0 + score[r, c]
    if best_site is None or tot < best_site[0]:
        best_site = (tot, r, c, hr, yaw)
_, r, c, hr, hall_yaw = best_site
gate = sea_bearing(h, X, Y, r, c, dx)
out['stronghold'] = dict(x=float(X[r, c]), y=float(Y[r, c]), z=float(h[r, c]), gate_deg=gate, wall_radius_m=38.0,
                         hall_yaw_deg=float(hall_yaw), hall_range_m=float(hr), fort_range_m=float(rng_fort[r, c]))
# Forest village (Lundvik): the generator's pick sits on a slope (the longhouse was buried 1.5 m uphill).
# Flattest longhouse-sized ground, 3-20 m up, 40-220 m from the shore, within 1.5 km of the original site.
h2, X2, Y2, dx2 = load('forest', 2.0)
d_sea2 = tl.distance_field(h2 <= 0, dx2)
rng_v = local_range(h2, int(12 / dx2))
score = rng_v + np.hypot(X2 - vil['x'], Y2 - vil['y']) / 1500.0
score[(h2 < 3) | (h2 > 20) | (d_sea2 < 40) | (d_sea2 > 220) | (np.hypot(X2 - vil['x'], Y2 - vil['y']) > 1500)] = np.nan
r, c = best(score)
out['forest_village'] = dict(x=float(X2[r, c]), y=float(Y2[r, c]), z=float(h2[r, c]), range_m=float(rng_v[r, c]))
del h2, X2, Y2, d_sea2, rng_v

wf = fp['waterfall']
out['waterfall'] = dict(lip_x=wf['x'], lip_y=wf['y'], lip_z=wf['z'], dir_deg=wf['dir_deg'])

# ---------------------------------------------------------------- glacier: rune circle + ice shrine
h, X, Y, dx = load('glacier', 2.0)
rng_c = local_range(h, int(11 / dx))
score = rng_c + 0.0015 * np.abs(h - 300.0)
score[(h < 40) | (h > 650)] = np.nan
r, c = best(score)
out['rune_circle'] = dict(x=float(X[r, c]), y=float(Y[r, c]), z=float(h[r, c]), range_m=float(rng_c[r, c]))
rc = (X[r, c], Y[r, c])
d_rc = np.hypot(X - rc[0], Y - rc[1])
rng_s = local_range(h, int(6 / dx))
score = rng_s + d_rc / 1500.0
score[(h < 650) | (d_rc < 250)] = np.nan
r2, c2 = best(score)
out['ice_shrine'] = dict(x=float(X[r2, c2]), y=float(Y[r2, c2]), z=float(h[r2, c2]), range_m=float(rng_s[r2, c2]),
                         yaw_deg=math.degrees(math.atan2(rc[1] - Y[r2, c2], rc[0] - X[r2, c2])))

# ---------------------------------------------------------------- ember: dragon lair on the caldera floor
cal = LAYOUT['islands']['ember']['pois']['caldera']
lake_r = 200.0
h, X, Y, dx = load('ember', 2.0)
rr_ = np.hypot(X - cal['x'], Y - cal['y'])
rng_l = local_range(h, int(12 / dx))
score = rng_l.copy()
score[(rr_ < 212) | (rr_ > 235)] = np.nan            # right at the lake's crusted edge (lake radius 200 m)
r, c = best(score)
lx, ly = float(X[r, c]), float(Y[r, c])
out['lair'] = dict(x=lx, y=ly, z=float(h[r, c]), centre_x=cal['x'], centre_y=cal['y'], floor_z=float(h[r, c]),
                   lake_radius_m=lake_r, lair_radius_m=float(rr_[r, c]), range_m=float(rng_l[r, c]),
                   facing_deg=math.degrees(math.atan2(cal['y'] - ly, cal['x'] - lx)))

# ---------------------------------------------------------------- coasts: wrecks, driftwood, beacon towers
coast = []
rng = np.random.default_rng(77)
for name, n_wreck, n_drift, n_beacon in (('main', 1, 2, 2), ('forest', 1, 2, 1), ('glacier', 1, 1, 1), ('ember', 1, 2, 1)):
    h, X, Y, dx = load(name)
    sea = h <= 0
    d_sea = tl.distance_field(sea, dx)
    s = tl.slope(h, dx)
    taken = [(out['stronghold']['x'], out['stronghold']['y'])] if name == 'forest' else []
    for v in ('village', 'village_b'):
        p = LAYOUT['islands'][name]['pois'].get(v)
        if p:
            taken.append((p['x'], p['y']))

    def pick(mask, score, kind, sep=500.0):
        sc = np.where(mask, score, np.nan)
        for tx, ty in taken:
            sc[np.hypot(X - tx, Y - ty) < sep] = np.nan
        if np.all(np.isnan(sc)):
            return None
        r, c = best(sc)
        taken.append((X[r, c], Y[r, c]))
        return dict(kind=kind, island=name, x=float(X[r, c]), y=float(Y[r, c]), z=float(h[r, c]),
                    sea_deg=sea_bearing(h, X, Y, r, c, dx))
    noise = rng.random(h.shape)
    beach = (h > 0.4) & (h < 3.0) & (d_sea < 40) & (s < 0.12)
    for _ in range(n_wreck):
        p = pick(beach, s * 4 + noise, 'wreck', 700.0)
        if p: coast.append(p)
    for _ in range(n_drift):
        p = pick(beach, s * 4 + noise, 'driftwood', 450.0)
        if p: coast.append(p)
    head = (h > 15) & (h < 90) & (d_sea > 25) & (d_sea < 120) & (local_range(h, int(6 / dx)) < 3.0)
    for _ in range(n_beacon):
        p = pick(head, -h / 90.0 + noise * 0.5, 'beacon', 1200.0)
        if p: coast.append(p)
out['coast'] = coast

json.dump(out, open(os.path.join(GEN, 'landmarks.json'), 'w'), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != 'coast'}, indent=1))
print('coast:', [(p['island'], p['kind'], round(p['z'], 1)) for p in coast])
