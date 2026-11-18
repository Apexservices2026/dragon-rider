"""Real-world elevation (GeoTIFF DEM) -> cropped, square-metre, sea-level-corrected island heightfield.

Used by gen_archipelago.py for the main fjord island (Copernicus GLO-30 tiles of the Sognefjord). Needs `tifffile`
(system Python). Run with `python -I` when reading downloaded files.

Steps: mosaic the tiles by their GeoTIFF tie points -> sample a local east/south metre grid (Catmull-Rom) ->
find the sea (near-zero DSM values connected to the window edge) -> give it a smooth shelf (depth grows with
distance from shore) -> drown the window edges along the real valleys so it becomes an island with a natural
ria coastline instead of a square cliff.
"""
import math

import numpy as np

import terrain_lib as tl


class DemMosaic:
    """Lat/lon sampler over one or more geographic (EPSG:4326) GeoTIFF tiles."""

    def __init__(self, paths):
        import tifffile
        self.tiles = []
        for p in paths:
            with tifffile.TiffFile(p) as t:
                page = t.pages[0]
                tags = {tag.name: tag.value for tag in page.tags.values()}
                data = page.asarray().astype(np.float32)
            sx, sy = tags['ModelPixelScaleTag'][:2]
            tp = tags['ModelTiepointTag']
            lon0, lat0 = tp[3] - tp[0] * sx, tp[4] + tp[1] * sy   # lon/lat of pixel (0, 0)'s corner
            self.tiles.append((data, lon0, lat0, sx, sy))

    def sample(self, lon, lat):
        out = np.full(lon.shape, np.nan)
        for data, lon0, lat0, sx, sy in self.tiles:
            h, w = data.shape
            fc = (lon - lon0) / sx - 0.5   # pixel-is-area: centre of pixel (0, 0) is half a pixel in
            fr = (lat0 - lat) / sy - 0.5
            inside = (fc >= -0.5) & (fc <= w - 0.5) & (fr >= -0.5) & (fr <= h - 0.5) & np.isnan(out)
            if inside.any():
                out[inside] = tl.sample_bicubic(data, fr[inside], fc[inside])
        if np.isnan(out).any():
            raise ValueError('DEM window leaves the tiles (%.1f%% missing)' % (100 * np.isnan(out).mean()))
        return out


def local_grid_lonlat(lon_c, lat_c, n, size_m):
    """lon/lat arrays for an n x n grid of `size_m` metres centred on (lon_c, lat_c); col = east, row = south."""
    X, Y = tl.grid(n, size_m)
    phi = math.radians(lat_c)
    m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    m_per_deg_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
    return lon_c + X / m_per_deg_lon, lat_c - Y / m_per_deg_lat


def build_dem_island(paths, lon_c, lat_c, size_m, n, exaggerate=1.1, sea_threshold=1.5, shelf_depth=140.0,
                     shelf_len=220.0, edge_fade=(300.0, 2800.0), drown=1700.0, seed=61, log=print):
    """Returns (height_m [n x n], info dict). Heights are metres above sea level; the sea is below 0."""
    dem = DemMosaic(paths)
    lon, lat = local_grid_lonlat(lon_c, lat_c, n, size_m)
    log('DEM: sampling %dx%d over %.1f km at (%.4f E, %.4f N)' % (n, n, size_m / 1000, lon_c, lat_c))
    h = dem.sample(lon, lat)
    del lon, lat
    dx = size_m / (n - 1)
    info = dict(raw_min=float(h.min()), raw_max=float(h.max()))

    # Sea: low DSM values connected to the window border (fjord water reads ~0 m, with noise and some negatives).
    low = h < sea_threshold
    sea = _connected_to_border(low)
    log('DEM: sea %.1f%% of window (raw %.0f..%.0f m)' % (100 * sea.mean(), info['raw_min'], info['raw_max']))

    land = np.maximum(h, 0.0) * exaggerate
    # Island mask: drown the window edges, deepest at the border; low ground floods first so the coast follows
    # the real valleys (a ria coast). Noise wobbles the fade so the outline isn't a rounded square.
    X, Y = tl.grid(n, size_m)
    # rounded-square distance to the window edge (a plain min() of the two axes leaves a crease on the diagonals)
    half = size_m / 2
    edge = half - (np.abs(X) ** 4 + np.abs(Y) ** 4) ** 0.25
    nz = tl.Perlin(seed)
    wob = tl.fbm(nz, X / 2500.0, Y / 2500.0, 4) * 900.0
    e = tl.smoothstep(edge_fade[0], edge_fade[1], edge + wob)
    land = land - (1.0 - e) ** 1.3 * drown
    land = np.where(sea, -1.0, land)
    del X, Y, edge, wob

    # Smooth shelf: depth grows with distance from the (new) shoreline, so coasts slope in instead of stepping.
    water = land <= 0.0
    d = tl.distance_field(~water, dx)
    depth = shelf_depth * (1.0 - np.exp(-d / shelf_len)) + 1.2
    out = np.where(water, -depth, land)
    # Blend the first few metres of shore so the land meets the shelf without a lip.
    shore = tl.smoothstep(0.0, 6.0, out)
    out = np.where(water, out, out * (0.35 + 0.65 * shore) + 0.0)
    info.update(sea_fraction=float(water.mean()), max_m=float(out.max()), min_m=float(out.min()))
    return out, info


def _connected_to_border(mask, factor=8):
    """Cells of `mask` connected (4-way) to the grid border. The flood runs on a 1/factor grid (about the DEM's own
    resolution) by repeated vectorised dilation, then is mapped back to full resolution."""
    n = mask.shape[0]
    c = mask[::factor, ::factor]
    reach = np.zeros_like(c)
    reach[0, :] = c[0, :]; reach[-1, :] = c[-1, :]; reach[:, 0] = c[:, 0]; reach[:, -1] = c[:, -1]
    while True:
        g = reach.copy()
        g[1:] |= reach[:-1]; g[:-1] |= reach[1:]; g[:, 1:] |= reach[:, :-1]; g[:, :-1] |= reach[:, 1:]
        g &= c
        if (g == reach).all():
            break
        reach = g
    # back to full res, grown by one coarse cell so the fine sea fills right up to the shoreline
    g = reach.copy()
    g[1:] |= reach[:-1]; g[:-1] |= reach[1:]; g[:, 1:] |= reach[:, :-1]; g[:, :-1] |= reach[:, 1:]
    full = np.repeat(np.repeat(g, factor, 0), factor, 1)[:n, :n]
    return full & mask
