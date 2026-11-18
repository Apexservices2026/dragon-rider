"""Procedural geometry for the archipelago landmarks (see build_landmarks.py).
Units metres, Z up, +X forward, origin at base centre unless the manifest says otherwise."""
import math

import bmesh
from mathutils import Matrix, Vector, noise

import kit_props as K
from kit_geo import MB, V, rng
from kit_props import RECT, ellipse

PI = math.pi


# =========================================================================== shared helpers
def icosphere(sub):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    vs = [v.co.copy() for v in bm.verts]
    fs = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return vs, fs


def rock(mb, base, size, mat, seed, sub=2, amp=0.35, freq=1.2, flat=0.25, rotz=None, warp=None, sink=0.0):
    """Noise-displaced boulder sitting on `base` (its flattened bottom at base.z - sink)."""
    vs, fs = icosphere(sub + 1)
    off = Vector((seed * 7.13, seed * 3.31, seed * 1.77))
    out = []
    for p in vs:
        n1 = noise.fractal(p * freq + off, 0.8, 2.1, 4)
        n2 = noise.noise(p * freq * 3.1 + off * 1.3)
        q = p * (1 + amp * n1 + amp * 0.25 * n2)
        q = Vector((q.x * size[0] / 2, q.y * size[1] / 2, q.z * size[2] / 2))
        if warp:
            q = warp(q)
        out.append(q)
    zmin = min(q.z for q in out)
    zmax = max(q.z for q in out)
    cut = zmin + (zmax - zmin) * flat
    R = Matrix.Rotation(rng.uniform(0, 2 * PI) if rotz is None else rotz, 3, "Z")
    out = [Vector(base) + R @ Vector((q.x, q.y, max(q.z, cut) - cut - sink)) for q in out]
    mb.poly(out, fs, mat, smooth=True)
    return out


def bend(mb, start, R):
    """Bend vertices added since `start` around a circle of radius R (centre at (0, -R)): +X -> arc."""
    for i in range(start, len(mb.V)):
        x, y, z = mb.V[i]
        th = x / R
        mb.V[i] = ((R + y) * math.sin(th), (R + y) * math.cos(th) - R, z)


def transform(mb, start, M, pivot=Vector((0, 0, 0))):
    for i in range(start, len(mb.V)):
        mb.V[i] = tuple(pivot + M @ (Vector(mb.V[i]) - pivot))


def ground_to_zero(mb):
    zmin = min(v[2] for v in mb.V)
    mb.V = [(x, y, z - zmin) for x, y, z in mb.V]


def carved_post(mb, p0, p1, r, mat="M_Wood", twist=5.0, seg=10, rings=24):
    """Post with spiral carving (helix bands) and a capital."""
    p0, p1 = Vector(p0), Vector(p1)
    path = [p0.lerp(p1, i / (rings - 1)) for i in range(rings)]
    sec = [(math.cos(2 * PI * k / seg), math.sin(2 * PI * k / seg)) for k in range(seg)]
    rows = []
    L = (p1 - p0).length
    for i, c in enumerate(path):
        f = i / (rings - 1)
        row = []
        for k, (cx, cy) in enumerate(sec):
            a = 2 * PI * k / seg
            band = 0.13 * max(0.0, math.sin(a * 2 + f * L * twist)) if 0.08 < f < 0.9 else 0.0
            rr = r * (1 + band - (0.12 if f > 0.93 else 0) + (0.18 if 0.88 < f < 0.93 else 0))
            row.append(c + Vector((cx * rr, cy * rr, 0)))
        rows.append(row)
    mb.grid(rows, mat, closed_u=True, want=lambda i, j: rows[i][j] - path[i])


def gable_roof(mb, x0, x1, half_w, eave_z, ridge_z, th, mat_top="M_Shingle", mat_under="M_Wood", nx=None,
               ridge_axis="x", y_off=0.0):
    """Straight gable roof slab spanning x0..x1, eaves at +-half_w. Shingle UV: rows along X, slope = +V."""
    nx = nx or max(2, int((x1 - x0) / 1.5))
    xs = [x0 + (x1 - x0) * k / nx for k in range(nx + 1)]
    qs = [0.0, 0.25, 0.5, 0.75, 1.0]
    run = math.hypot(half_w, ridge_z - eave_z)
    nrm_y = (ridge_z - eave_z) / run
    nrm_z = half_w / run

    def P(x, q, side, top):
        y = side * half_w * (1 - q) + y_off
        z = eave_z + (ridge_z - eave_z) * q
        if top:
            y += side * nrm_y * th
            z += nrm_z * th
        return V(x, y, z) if ridge_axis == "x" else V(y, x, z)
    m = 2.0
    for side in (1, -1):
        o = (rng.random(), rng.random())
        rows = [[P(x, q, side, True) for x in xs] for q in qs]
        mb.grid(rows, mat_top, uv=lambda i, j, xs=xs, o=o: ((xs[j] - x0) / m + o[0], qs[i] * run / m + o[1]),
                want=(V(0, side * nrm_y, nrm_z) if ridge_axis == "x" else V(side * nrm_y, 0, nrm_z)))
        rows = [[P(x, q, side, False) for x in xs] for q in qs]
        mb.grid(rows, mat_under, want=(V(0, -side * 0.3, -1) if ridge_axis == "x" else V(-side * 0.3, 0, -1)))
        rows = [[P(x, 0, side, False) for x in xs], [P(x, 0, side, True) for x in xs]]
        mb.grid(rows, mat_under, want=(V(0, side, -0.2) if ridge_axis == "x" else V(side, 0, -0.2)))
        for xe, sg in ((x0, -1), (x1, 1)):
            rows = [[P(xe, q, side, False), P(xe, q, side, True)] for q in qs]
            mb.grid(rows, mat_under, want=(V(sg, 0, 0) if ridge_axis == "x" else V(0, sg, 0)))
    # ridge board
    if ridge_axis == "x":
        mb.box(((x0 + x1) / 2, y_off, ridge_z + th + 0.05), (x1 - x0 + 0.1, 0.3, 0.18), "M_WoodTar")
    else:
        mb.box((y_off, (x0 + x1) / 2, ridge_z + th + 0.05), (0.3, x1 - x0 + 0.1, 0.18), "M_WoodTar")


def lean_to(mb, x0, x1, y_in, y_out, z_in, z_out, th, nx=10):
    """Single-pitch shingle roof from the wall (y_in, z_in) down to the eave (y_out, z_out)."""
    xs = [x0 + (x1 - x0) * k / nx for k in range(nx + 1)]
    sg = 1 if y_out > y_in else -1
    run = math.hypot(y_out - y_in, z_out - z_in)
    n = Vector((0, (y_out - y_in), run * 0 + abs(y_out - y_in) * 0 + 0)).normalized()
    up = Vector((0, sg * (z_in - z_out), abs(y_out - y_in))).normalized()
    o = (rng.random(), rng.random())
    qs = [0.0, 0.5, 1.0]

    def P(x, q, top):
        p = Vector((x, y_out + (y_in - y_out) * q, z_out + (z_in - z_out) * q))
        return p + up * th if top else p
    rows = [[P(x, q, True) for x in xs] for q in qs]
    mb.grid(rows, "M_Shingle", uv=lambda i, j: ((xs[j] - x0) / 2 + o[0], qs[i] * run / 2 + o[1]), want=up)
    rows = [[P(x, q, False) for x in xs] for q in qs]
    mb.grid(rows, "M_Wood", want=-up)
    rows = [[P(x, 0, False) for x in xs], [P(x, 0, True) for x in xs]]
    mb.grid(rows, "M_Wood", want=(0, sg, 0))
    _ = n


def plank_wall(mb, a, b, z0, ztop, nrm, mat="M_Wood", width=0.3, skip=None):
    """Vertical board wall from point a to b (xy), top height ztop(t) along the wall (t 0..1)."""
    a, b = Vector(a), Vector(b)
    L = (b - a).length
    n = max(1, int(L / width))
    nv = Vector((nrm[0], nrm[1])).normalized()
    n3 = Vector((nv.x, nv.y, 0))
    for k in range(n):
        t0, t1 = k / n, (k + 1) / n
        if skip and skip((t0 + t1) / 2 * L):
            continue
        off = nv * (0.035 if k % 2 else 0.0)
        p0 = a.lerp(b, t0) + off
        p1 = a.lerp(b, t1) + off
        z0a, z1a = ztop(t0), ztop(t1)
        if max(z0a, z1a) <= z0 + 0.01:
            continue
        q = [V(p0.x, p0.y, z0), V(p1.x, p1.y, z0), V(p1.x, p1.y, z1a), V(p0.x, p0.y, z0a)]
        o = (rng.random(), rng.random())
        mb.face([mb.v(p) for p in q], [(o[0], o[1]), (o[0] + width / 2, o[1]), (o[0] + width / 2, o[1] + (z1a - z0) / 2),
                                       (o[0], o[1] + (z0a - z0) / 2)], mat, False, n3)
        if k % 2:
            for pp, zt, sg in ((p0, z0a, -1), (p1, z1a, 1)):
                base = pp - off
                q = [V(base.x, base.y, z0), V(pp.x, pp.y, z0), V(pp.x, pp.y, zt), V(base.x, base.y, zt)]
                mb.face([mb.v(p) for p in q], [(0, 0), (0.02, 0), (0.02, 1), (0, 1)], mat, False, Vector(((b - a).x, (b - a).y, 0)).normalized() * sg)


def dragon_finial(mb, base, direction, scale):
    """Kit dragon head (eyes on) scaled and turned to face `direction` (+1 = +X, -1 = -X)."""
    n0 = len(mb.V)
    K.build_dragon_head(mb, Vector((0, 0, 0)), pitch=-4.0)
    M = Matrix.Diagonal((scale, scale, scale))
    if direction < 0:
        M = Matrix.Rotation(PI, 3, "Z") @ M
    transform(mb, n0, M)
    for i in range(n0, len(mb.V)):
        mb.V[i] = tuple(Vector(mb.V[i]) + Vector(base))


# =========================================================================== 1. CLAN STRONGHOLD
def build_mead_hall():
    mb = MB("SM_MeadHall")
    L, W, wall_h, ridge = 40.0, 12.0, 4.6, 15.5
    hw = W / 2
    over = 0.5
    gover = 0.8
    eave = wall_h - over * (ridge - wall_h) / hw * 0.95
    door_w = 2.4
    # stone footing
    for sx in (-1, 1):
        mb.box((0, sx * hw, 0.15), (L + 0.6, 0.7, 0.4), "M_Stone")
        mb.box((sx * L / 2, 0, 0.15), (0.7, W + 0.6, 0.4), "M_Stone")
    # long walls (stave boards)
    for side in (1, -1):
        plank_wall(mb, (-L / 2, side * hw), (L / 2, side * hw), 0.2, lambda t: wall_h + 0.3, (0, side, 0), width=0.34,
                   skip=(lambda s: abs(s - L / 2 - 6) < 1.0) if side > 0 else None)
        mb.box((0, side * hw, wall_h + 0.15), (L + 0.4, 0.45, 0.35), "M_WoodTar")  # wall plate
    plank_wall(mb, (6 - 1.0, hw), (6 + 1.0, hw), 2.45, lambda t: wall_h + 0.3, (0, 1, 0), width=0.34)
    # side door on +Y
    mb.box((6, hw + 0.05, 1.25), (1.8, 0.1, 2.4), "M_Wood")
    for s in (-1, 1):
        carved_post(mb, (6 + s * 1.15, hw + 0.25, 0.2), (6 + s * 1.15, hw + 0.25, 2.9), 0.16, rings=14, seg=8)
    mb.box((6, hw + 0.25, 3.0), (2.8, 0.3, 0.3), "M_WoodTar")

    # gables with door at +X
    def gable_top(t, x):
        y = -hw + W * t
        return eave + (ridge - eave) * (1 - abs(y) / (hw + over)) - 0.05
    for sx in (-1, 1):
        x = sx * L / 2
        plank_wall(mb, (x, -hw), (x, hw), 0.2, lambda t: gable_top(t, x), (sx, 0, 0), width=0.34,
                   skip=(lambda s: abs(s - hw) < door_w / 2 + 0.05) if sx > 0 else None)
    plank_wall(mb, (L / 2, -door_w / 2 - 0.05), (L / 2, door_w / 2 + 0.05), 3.6,
               lambda t: gable_top((hw - door_w / 2 - 0.05 + (door_w + 0.1) * t) / W, L / 2), (1, 0, 0), width=0.34)
    # main roof
    gable_roof(mb, -L / 2 - gover, L / 2 + gover, hw + over, eave, ridge, 0.28, nx=26)
    # corner posts
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.cyl((sx * L / 2, sy * hw, 0.2), (sx * L / 2, sy * hw, wall_h + 0.3), 0.32, seg=10, mat="M_WoodTar")
    # gable bargeboards crossing at the apex + dragon-head finials facing outward
    for sx in (-1, 1):
        x = sx * (L / 2 + gover + 0.06)
        apex = V(x, 0, ridge + 0.3)
        for side in (1, -1):
            e = V(x, side * (hw + over + 0.1), eave + 0.2)
            d = (apex - e).normalized()
            end = apex + d * 1.6
            mb.tube([e, e.lerp(apex, 0.5), apex, end], RECT, (0.06, 0.32), "M_WoodTar", side=(1, 0, 0), cap0=True, cap1=True)
        # dragon neck rising from the ridge end, head facing out
        neck = [V(sx * (L / 2 + gover - 0.8), 0, ridge + 0.2), V(sx * (L / 2 + gover + 0.3), 0, ridge + 0.8),
                V(sx * (L / 2 + gover + 1.0), 0, ridge + 1.9), V(sx * (L / 2 + gover + 1.3), 0, ridge + 2.9)]
        mb.tube(neck, ellipse(10, 2.4), [(0.22, 0.3), (0.24, 0.32), (0.25, 0.32), (0.26, 0.33)], "M_WoodTar",
                side=(0, 1, 0))
        dragon_finial(mb, neck[-1] + V(sx * 0.15, 0, 0.0), sx, 2.1)
    # ridge crest: small carved crosses / spikes along the ridge
    for k in range(13):
        x = -L / 2 + 3 + (L - 6) * k / 12
        mb.cone((x, 0, ridge + 0.4), (x, 0, ridge + 1.1), 0.12, seg=4, mat="M_WoodTar")
    # smoke louvres (two turrets)
    for x in (-8, 8):
        z0 = ridge - 0.9
        mb.box((x, 0, z0 + 0.8), (1.6, 1.6, 1.6), "M_WoodTar")
        mb.cone((x, 0, z0 + 1.6), (x, 0, z0 + 3.0), 1.35, seg=4, mat="M_Shingle", cap=True)
    # svalgang gallery along both long sides
    for side in (1, -1):
        gy = side * (hw + 2.4)
        for k in range(14):
            x = -L / 2 + 1 + (L - 2) * k / 13
            mb.cyl((x, gy, 0.2), (x, gy, 2.6), 0.13, seg=7, mat="M_Wood")
            mb.box((x, side * (hw + 1.2), 2.55), (0.15, 2.4, 0.18), "M_Wood")
        mb.box((0, gy, 1.05), (L - 1.6, 0.08, 0.6), "M_Wood")
        mb.box((0, gy, 2.65), (L - 1.6, 0.22, 0.22), "M_WoodTar")
        lean_to(mb, -L / 2 + 0.5, L / 2 - 0.5, side * (hw - 0.1), side * (hw + 3.0), 3.62, 2.6, 0.12)
    # entrance porch at +X
    px0, px1 = L / 2, L / 2 + 4.2
    for s in (-1, 1):
        carved_post(mb, (px1 - 0.3, s * 2.4, 0.2), (px1 - 0.3, s * 2.4, 4.2), 0.24)
        carved_post(mb, (px0 + 0.35, s * (door_w / 2 + 0.35), 0.2), (px0 + 0.35, s * (door_w / 2 + 0.35), 4.0), 0.26,
                    twist=7)
    mb.box((px1 - 0.3, 0, 4.25), (0.35, 5.4, 0.35), "M_WoodTar")
    gable_roof(mb, px0 - 0.5, px1 + 0.6, 3.2, 3.9, 7.2, 0.2, nx=4)
    mb.box((px0 + 0.04, 0, 1.9), (0.12, door_w, 3.4), "M_Wood")
    for z in (0.8, 1.9, 3.0):
        mb.box((px0 + 0.12, 0, z), (0.03, door_w * 0.92, 0.1), "M_Iron")
    for s in (-1, 1):
        mb.sphere((px0 + 0.16, s * 0.35, 1.7), 0.09, "M_Iron", seg=6, rings=4)
    mb.box((px0 + 2.2, 0, 0.1), (4.6, 5.6, 0.25), "M_Stone")
    # porch gable dragon
    mb.tube([V(px1 + 0.4, 0, 7.3), V(px1 + 0.9, 0, 8.1), V(px1 + 1.1, 0, 8.8)], ellipse(8, 2.4),
            [(0.14, 0.2), (0.15, 0.21), (0.16, 0.22)], "M_WoodTar", side=(0, 1, 0))
    dragon_finial(mb, V(px1 + 1.2, 0, 8.85), 1, 1.3)
    return mb


def build_gatehouse():
    """Two stone bastions + timber gate storey. Wall line along Y, passage along X (outside = +X)."""
    mb = MB("SM_Gatehouse")
    gap = 4.2
    bw, bd, bh = 5.0, 6.0, 6.0
    for sy in (-1, 1):
        cy = sy * (gap / 2 + bw / 2)
        # battered stone bastion: loft of 4 rings
        rows = []
        for z, f in ((0.0, 1.0), (2.0, 0.97), (4.0, 0.94), (bh, 0.92)):
            hx, hy = bd / 2 * f, bw / 2 * f
            rows.append([V(hx, cy - hy, z), V(hx, cy + hy, z), V(-hx, cy + hy, z), V(-hx, cy - hy, z)])
        mb.grid(rows, "M_Stone", closed_u=True, smooth=False, want=lambda i, j, rows=rows, cy=cy:
                (rows[i][j] + rows[i][(j + 1) % 4]) / 2 - V(0, cy, rows[i][j].z))
        mb.cap(rows[-1], "M_Stone", (0, 0, 1))
        # corner quoins (bigger stones)
        for sx in (-1, 1):
            for k in range(5):
                z = 0.5 + k * 1.15
                f = 1.0 - 0.08 * z / bh
                mb.box((sx * bd / 2 * f, cy + sy * bw / 2 * f * (1 if k % 2 else -1) * 0.75, z), (0.6, 1.2, 0.9), "M_Stone",
                       rot=(0, 0, rng.uniform(-0.05, 0.05)))
        # timber parapet on the bastion
        plank_wall(mb, (bd / 2 * 0.92, cy - bw / 2 * 0.92), (bd / 2 * 0.92, cy + bw / 2 * 0.92), bh, lambda t: bh + 1.3,
                   (1, 0, 0))
        plank_wall(mb, (-bd / 2 * 0.92, cy + bw / 2 * 0.92), (-bd / 2 * 0.92, cy - bw / 2 * 0.92), bh, lambda t: bh + 1.1,
                   (-1, 0, 0))
        oy = cy + sy * bw / 2 * 0.92
        plank_wall(mb, (-bd / 2 * 0.92, oy), (bd / 2 * 0.92, oy), bh, lambda t: bh + 1.2, (0, sy, 0))
    # gate storey bridging the passage
    zf = 4.4
    mb.box((0, 0, zf), (bd, gap + 0.6, 0.4), "M_WoodTar")
    for sx in (-1, 1):
        plank_wall(mb, (sx * bd / 2 * 0.9, -gap / 2 - 0.3), (sx * bd / 2 * 0.9, gap / 2 + 0.3), zf + 0.2, lambda t: 8.4,
                   (sx, 0, 0))
    for sy in (-1, 1):
        for sx in (-1, 1):
            mb.cyl((sx * bd / 2 * 0.9, sy * (gap / 2 + 0.3), 0), (sx * bd / 2 * 0.9, sy * (gap / 2 + 0.3), 8.6), 0.22,
                   seg=8, mat="M_WoodTar")
    gable_roof(mb, -gap / 2 - bw - 0.4, gap / 2 + bw + 0.4, bd / 2 + 0.7, 8.2, 11.4, 0.22, nx=8, ridge_axis="y")
    # windows (dark slots) on the outer face
    for y in (-1.2, 0, 1.2):
        mb.box((bd / 2 * 0.9 + 0.05, y, 6.7), (0.06, 0.35, 0.8), "M_WoodTar")
    # gates (two leaves, one ajar)
    for sy, ang in ((-1, 0.0), (1, math.radians(35))):
        hinge = V(bd / 2 * 0.6, sy * gap / 2, 0)
        R = Matrix.Rotation(-ang * sy, 3, "Z")
        for k in range(7):
            c = hinge + R @ V(0, -sy * (0.15 + 0.3 * k), 1.9)
            mb.box(c, (0.12, 0.28, 3.8), "M_Wood", rot=R)
        for z in (0.6, 1.9, 3.2):
            mb.box(hinge + R @ V(0.08, -sy * gap / 4, z), (0.03, gap / 2 - 0.1, 0.1), "M_Iron", rot=R)
    # dragon finials on the roof gables (facing outward +-Y... keep facing +X / -X for the passage axis)
    mb.box((0, 0, 0.05), (bd + 2, gap, 0.1), "M_Stone")
    return mb


FORT_SEG = 8.0
FORT_CURVE_R = FORT_SEG / math.radians(15)


def build_fort_wall(curved=False):
    """Earth rampart + palisade + fighting platform, 8 m along X, inside = -Y. 16 subdivisions along X so it
    also works as an Unreal spline mesh. curved=True bakes a 15 deg bend (24 segments = full ring, R 30.6 m)."""
    mb = MB("SM_FortWallCurve15" if curved else "SM_FortWall")
    start = len(mb.V)
    nx = 16
    xs = [-FORT_SEG / 2 + FORT_SEG * k / nx for k in range(nx + 1)]
    prof = [(-6.0, 0.0), (-4.0, 0.9), (-2.2, 2.2), (-0.9, 2.6), (0.6, 2.6), (1.6, 1.8), (3.0, 0.0), (4.2, -1.2),
            (5.4, -1.0), (6.6, 0.0)]
    rows = []
    for x in xs:
        rows.append([V(x, y, z + 0.06 * math.sin(x * 1.3 + y)) for y, z in prof])
    mb.grid(rows, "M_Turf", want=(0, 0, 1))
    # palisade along the rampart crest (outer edge)
    n = int(FORT_SEG / 0.3)
    for k in range(n):
        x = -FORT_SEG / 2 + FORT_SEG * (k + 0.5) / n
        r = rng.uniform(0.13, 0.16)
        h = rng.uniform(3.0, 3.4)
        b = V(x, 0.9, 1.9)
        t = V(x + rng.uniform(-0.04, 0.04), 0.9 + rng.uniform(-0.04, 0.04), 2.6 + h)
        mb.tube([b, b.lerp(t, 0.5), t], ellipse(7), [r, r * 0.97, r * 0.92], "M_Wood", side=(1, 0, 0))
        mb.cone(t, t + V(0, 0, 0.4), r * 0.92, seg=7, mat="M_Wood", cap=False)
    # fighting platform behind the palisade
    for k in range(10):
        x = -FORT_SEG / 2 + FORT_SEG * (k + 0.5) / 10
        mb.box((x, 0.0, 3.85), (FORT_SEG / 10 - 0.04, 1.4, 0.08), "M_Wood")
    for k in range(4):
        x = -FORT_SEG / 2 + 1 + (FORT_SEG - 2) * k / 3
        mb.cyl((x, -0.6, 2.4), (x, -0.6, 3.8), 0.1, seg=6, mat="M_Wood")
    mb.box((0, 0.65, 3.0), (FORT_SEG, 0.12, 0.2), "M_Wood")
    mb.box((0, 0.65, 4.6), (FORT_SEG, 0.12, 0.2), "M_Wood")
    if curved:
        bend(mb, start, FORT_CURVE_R)
    return mb


# =========================================================================== 2. RUNE CIRCLE
def runestone(mb, base, h, w, d, column, seed, rotz=0.0):
    """Standing stone slab; the broad faces (+-Y) carry atlas column `column` of T_Runes."""
    start = len(mb.V)
    seg = 16
    nr = 14
    rows = []
    off = Vector((seed * 5.1, seed * 2.3, seed * 0.7))
    for i in range(nr):
        f = i / (nr - 1)
        z = -0.4 + (h + 0.4) * f
        taper = 1.0 - 0.18 * f
        top = math.sqrt(max(0.0, 1 - max(0.0, (f - 0.82) / 0.18) ** 2)) if f > 0.82 else 1.0
        row = []
        for k in range(seg):
            a = 2 * PI * k / seg
            cx, cy = math.cos(a), math.sin(a)
            sx = math.copysign(abs(cx) ** 0.35, cx) * w / 2 * taper * (0.3 + 0.7 * top)
            sy = math.copysign(abs(cy) ** 0.35, cy) * d / 2 * taper * (0.5 + 0.5 * top)
            p = Vector((sx, sy, z if f < 0.99 else h))
            nz = noise.fractal(p * 0.9 + off, 0.8, 2.0, 3)
            p += Vector((cx, cy, 0)) * 0.06 * nz
            row.append(p)
        rows.append(row)
    ids = [[mb.v(p) for p in row] for row in rows]
    ci = column % 4
    for i in range(nr - 1):
        for k in range(seg):
            k1 = (k + 1) % seg
            q = [ids[i][k], ids[i][k1], ids[i + 1][k1], ids[i + 1][k]]
            pts = [Vector(mb.V[j]) for j in q]
            c = sum(pts, Vector()) / 4
            nrm = Vector((c.x, c.y * (w / d) ** 2, 0)).normalized()
            if abs(nrm.y) > 0.75:
                sgn = 1 if nrm.y > 0 else -1
                uvs = [((ci + min(max(0.5 - sgn * p.x / w * 0.98, 0.005), 0.995)) / 4, min(max((p.z + 0.05) / (h + 0.1), 0), 1))
                       for p in pts]
                mb.face(q, uvs, "M_Runes", True, nrm)
            else:
                o = (seed * 0.37 % 1, seed * 0.71 % 1)
                uvs = [((p.x + p.y) / 4 + o[0], p.z / 4 + o[1]) for p in pts]
                mb.face(q, uvs, "M_Rock", True, nrm)
    mb.cap(rows[-1], "M_Rock", (0, 0, 1))
    transform(mb, start, Matrix.Rotation(rotz, 3, "Z"))
    for i in range(start, len(mb.V)):
        mb.V[i] = tuple(Vector(mb.V[i]) + Vector(base))


RUNE_SIZES = [(4.6, 1.5, 0.55), (3.8, 1.3, 0.5), (4.2, 1.6, 0.6), (3.5, 1.2, 0.45)]


def build_runestone(i):
    mb = MB(f"SM_Runestone_{'ABCD'[i]}")
    h, w, d = RUNE_SIZES[i]
    runestone(mb, V(0, 0, 0), h, w, d, i, seed=11 + i)
    return mb


def build_altar():
    mb = MB("SM_RuneAltar")
    for sx in (-1, 1):
        rock(mb, V(sx * 0.9, 0, 0), (0.9, 1.3, 1.1), "M_Rock", seed=31 + sx, sub=2, amp=0.2, flat=0.1)
    start = len(mb.V)
    rock(mb, V(0, 0, 0), (3.2, 1.8, 0.55), "M_RockFrost", seed=33, sub=3, amp=0.12, flat=0.0, rotz=0.0)
    for i in range(start, len(mb.V)):
        x, y, z = mb.V[i]
        mb.V[i] = (x, y, z + 0.85)
    return mb


def build_frost_boulder(i):
    mb = MB(f"SM_FrostBoulder_{'ABC'[i]}")
    sizes = [(3.2, 2.6, 2.2), (2.0, 1.7, 1.5), (4.5, 3.0, 2.8)]
    rock(mb, V(0, 0, 0), sizes[i], "M_RockFrost", seed=41 + i, sub=3, amp=0.33, freq=1.0, flat=0.2, rotz=0.0)
    return mb


def ice_prism(mb, base, h, r, seed, lean=(0, 0)):
    seg = 6
    rows = []
    for i, f in enumerate((0.0, 0.45, 0.8, 0.92)):
        rr = r * (1 - 0.15 * f) * (1 + 0.1 * math.sin(seed * 3 + i))
        c = Vector(base) + Vector((lean[0] * f * h, lean[1] * f * h, -0.3 + (h + 0.3) * f))
        rows.append([c + Vector((rr * math.cos(2 * PI * k / seg + seed), rr * math.sin(2 * PI * k / seg + seed), 0))
                     for k in range(seg)])
    cen = [sum(rw, Vector()) / seg for rw in rows]
    mb.grid(rows, "M_Ice", closed_u=True, smooth=False, want=lambda i, j: rows[i][j] - cen[i])
    tip = Vector(base) + Vector((lean[0] * h * 1.02, lean[1] * h * 1.02, h * 1.1))
    ti = mb.v(tip)
    ids = [mb.v(p) for p in rows[-1]]
    for k in range(seg):
        mb.face([ids[k], ids[(k + 1) % seg], ti], [(0, 0), (0.3, 0), (0.15, 0.4)], "M_Ice", False, rows[-1][k] - cen[-1])


def build_ice_shrine():
    """Ice archway: crystal pillars, a jagged ice arch with icicles, rune altar slab beneath. Passage along X."""
    mb = MB("SM_IceShrine")
    span = 3.6
    for sy in (-1, 1):
        for k, (dx, dy, h, r) in enumerate(((0, 0, 6.2, 0.75), (0.7, 0.45, 4.4, 0.45), (-0.6, 0.5, 3.6, 0.4),
                                             (0.2, -0.6, 2.6, 0.35), (-0.5, -0.4, 5.0, 0.4))):
            ice_prism(mb, V(dx, sy * span + dy * sy, 0), h, r, seed=k * 1.7 + sy,
                      lean=(rng.uniform(-0.05, 0.05), sy * rng.uniform(0.0, 0.06)))
    # arch: hexagonal jagged section along a pointed arch
    path = []
    for k in range(17):
        a = PI * k / 16
        y = -span * math.cos(a)
        z = 5.6 + 3.4 * math.sin(a) ** 0.8
        path.append(V(0, y, z))
    sec = [(math.cos(2 * PI * k / 6), math.sin(2 * PI * k / 6)) for k in range(6)]
    sc = [(0.55 + 0.15 * math.sin(k * 1.7), 0.7 + 0.2 * math.cos(k * 2.3)) for k in range(17)]
    mb.tube(path, sec, sc, "M_Ice", side=(1, 0, 0), cap0=True, cap1=True, smooth=False)
    # spikes on the crown and icicles beneath
    for k in range(2, 15):
        p = path[k]
        a = PI * k / 16
        outv = V(0, -math.cos(a), math.sin(a)).normalized()
        if k % 2 == 0:
            mb.cone(p + outv * 0.4, p + outv * rng.uniform(1.2, 2.2) + V(rng.uniform(-0.3, 0.3), 0, 0), 0.25, seg=5,
                    mat="M_Ice")
        mb.cone(p - outv * 0.4, p - outv * 0.4 + V(0, 0, -rng.uniform(0.6, 1.6)), 0.12, seg=5, mat="M_Ice")
    # frozen step / rune slab under the arch
    rock(mb, V(0, 0, 0), (2.8, 5.2, 0.6), "M_RockFrost", seed=55, sub=2, amp=0.1, flat=0.0, rotz=0.0)
    return mb


def build_rune_circle():
    """Assembled landmark: 7 runestones facing the centre + altar (individual pieces also exported)."""
    mb = MB("SM_RuneCircle")
    R = 9.0
    for k in range(7):
        a = 2 * PI * k / 7 + 0.2
        h, w, d = RUNE_SIZES[k % 4]
        h *= rng.uniform(0.9, 1.1)
        runestone(mb, V(R * math.cos(a), R * math.sin(a), 0), h, w, d, k % 4, seed=60 + k, rotz=a + PI / 2)
    for sx in (-1, 1):
        rock(mb, V(sx * 0.9, 0, 0), (0.9, 1.3, 1.1), "M_Rock", seed=71 + sx, sub=2, amp=0.2, flat=0.1)
    s0 = len(mb.V)
    rock(mb, V(0, 0, 0), (3.2, 1.8, 0.55), "M_RockFrost", seed=73, sub=3, amp=0.12, flat=0.0, rotz=0.0)
    for i in range(s0, len(mb.V)):
        x, y, z = mb.V[i]
        mb.V[i] = (x, y, z + 0.85)
    return mb


# =========================================================================== 3. DRAGON LAIR
def bone(mb, a, b, r, seg=6):
    a, b = Vector(a), Vector(b)
    path = [a.lerp(b, f) for f in (0, 0.08, 0.3, 0.7, 0.92, 1.0)]
    sc = [r * 1.0, r * 1.5, r * 0.75, r * 0.7, r * 1.4, r * 0.9]
    mb.tube(path, ellipse(seg), sc, "M_Bone", side=(0, 0, 1) if abs((b - a).normalized().z) < 0.9 else (1, 0, 0),
            cap0=True, cap1=True)


def nest_z(r):
    if r < 4.0:
        return 0.35 + 0.04 * r * r
    if r < 7.0:
        return 0.99 + (r - 4.0) / 3.0 * 1.6
    if r < 10.5:
        return 2.59 * (1 - ((r - 7.0) / 3.5) ** 1.5)
    return 0.0


def build_nest():
    mb = MB("SM_DragonNest")
    # ash / lava-grit mound
    nr, ns = 14, 28
    rows = []
    for i in range(nr + 1):
        r = 10.6 * i / nr
        rows.append([V(r * math.cos(2 * PI * k / ns), r * math.sin(2 * PI * k / ns),
                       nest_z(r) + 0.15 * noise.noise(Vector((r * math.cos(2 * PI * k / ns), r * math.sin(2 * PI * k / ns), 0)) * 0.4))
                     for k in range(ns)])
    mb.grid(rows, "M_LavaRock", closed_u=True, want=(0, 0, 1))
    # charred timbers woven around the rim
    for k in range(150):
        a = rng.uniform(0, 2 * PI)
        r = rng.uniform(4.6, 9.6)
        c = V(r * math.cos(a), r * math.sin(a), 0)
        ln = rng.uniform(2.5, 6.5)
        rad = rng.uniform(0.12, 0.32)
        ta = a + PI / 2 + rng.uniform(-0.5, 0.5)
        d = V(math.cos(ta), math.sin(ta), rng.uniform(-0.25, 0.35)).normalized()
        p0, p1 = c - d * ln / 2, c + d * ln / 2
        z0 = nest_z(math.hypot(p0.x, p0.y)) + rad * 0.6 + rng.uniform(0, 0.5)
        z1 = nest_z(math.hypot(p1.x, p1.y)) + rad * 0.6 + rng.uniform(0, 0.5)
        mb.cyl(V(p0.x, p0.y, z0), V(p1.x, p1.y, z1), rad, rad * rng.uniform(0.7, 1.0), seg=6, mat="M_Charred")
    # bones
    for k in range(26):
        a = rng.uniform(0, 2 * PI)
        r = rng.uniform(2.0, 9.0)
        c = V(r * math.cos(a), r * math.sin(a), 0)
        ln = rng.uniform(0.8, 2.6)
        ta = rng.uniform(0, 2 * PI)
        d = V(math.cos(ta), math.sin(ta), rng.uniform(-0.2, 0.3)).normalized()
        p0, p1 = c - d * ln / 2, c + d * ln / 2
        z = nest_z(r) + 0.12
        bone(mb, V(p0.x, p0.y, z + 0.1), V(p1.x, p1.y, z + d.z * ln / 2 + 0.1), rng.uniform(0.06, 0.12))
    # broken shields (plunder) leaning on the rim
    for k in range(12):
        a = 2 * PI * k / 12 + rng.uniform(-0.2, 0.2)
        r = rng.uniform(5.0, 6.5)
        c = V(r * math.cos(a), r * math.sin(a), nest_z(r) + 0.35)
        nrm = V(-math.cos(a), -math.sin(a), rng.uniform(0.4, 1.5)).normalized()
        K.build_shield(mb, c, nrm, rng.randrange(16), seg=12)
    # three dragon eggs
    for k, (x, y) in enumerate(((0.6, 0.4), (-0.9, 0.5), (0.1, -1.0))):
        mb.sphere(V(x, y, nest_z(0.8) + 0.85), 0.62, "M_Obsidian", seg=14, rings=9, scale=(1, 1, 1.45))
    ground_to_zero(mb)
    return mb


def build_dragon_skull():
    mb = MB("SM_DragonSkull")
    K.build_dragon_head(mb, V(0, 0, 0), pitch=0.0, eyes=False)
    mb.remap({"M_WoodTar": "M_Bone", "M_Wood": "M_Bone"})
    S = 5.0
    transform(mb, 0, Matrix.Diagonal((S, S, S)))
    # hollow eye sockets
    for sgn in (1, -1):
        mb.sphere(V(0.27 * S, sgn * 0.15 * S, 0.12 * S), 0.07 * S, "M_Charred", seg=8, rings=5, scale=(1.3, 0.6, 1.0))
    # tilt to rest the lower jaw on the ground
    transform(mb, 0, Matrix.Rotation(math.radians(-14), 3, "Y"))
    xs = [v[0] for v in mb.V]
    cx = (min(xs) + max(xs)) / 2
    mb.V = [(x - cx, y, z) for x, y, z in mb.V]
    ground_to_zero(mb)
    for i in range(len(mb.V)):
        x, y, z = mb.V[i]
        mb.V[i] = (x, y, z - 0.25)   # sink slightly into the grit
    return mb


def build_dragon_ribs():
    """Half-buried spine + ribcage, ~16 m along X."""
    mb = MB("SM_DragonRibs")
    spine = [V(-8 + 16 * k / 20, 0.3 * math.sin(k * 0.4), 2.2 * math.sin(PI * k / 20) ** 0.7 + 0.2) for k in range(21)]
    mb.tube(spine, ellipse(8), [0.32 - 0.14 * abs(k - 8) / 12 for k in range(21)], "M_Bone", side=(0, 1, 0), cap0=True,
            cap1=True)
    for k in range(1, 20):
        p = spine[k]
        mb.cone(p, p + V(-0.2, 0, 0.8 - 0.03 * abs(k - 8)), 0.12, seg=5, mat="M_Bone")
    for k in range(3, 16, 2):
        p = spine[k]
        size = 1.0 - abs(k - 8) / 14
        for sy in (-1, 1):
            pts = []
            for j in range(9):
                f = j / 8
                a = PI * 0.95 * f
                y = sy * (0.2 + 3.4 * size * math.sin(a))
                z = p.z + 0.3 * size + 1.0 * size * math.cos(a) - (p.z + 1.4) * f ** 1.6
                pts.append(V(p.x - 0.9 * f, y, z))
            mb.tube(pts, ellipse(6), [0.16 * size + 0.04 - 0.06 * f * size for f in [j / 8 for j in range(9)]], "M_Bone",
                    side=(1, 0, 0), cap1=True)
    ground_to_zero(mb)
    mb.V = [(x, y, z - 0.35) for x, y, z in mb.V]
    return mb


def spire(mb, base, h, r, seed, mat="M_Obsidian", sides=5, bend_v=(0, 0)):
    rows = []
    rs = [r, r * 0.8, r * 0.55, r * 0.28]
    fs = [0.0, 0.35, 0.68, 0.9]
    for i, (f, rr) in enumerate(zip(fs, rs)):
        c = Vector(base) + Vector((bend_v[0] * f * f * h, bend_v[1] * f * f * h, -0.4 + (h + 0.4) * f))
        rows.append([c + Vector((rr * (1 + 0.25 * math.sin(seed + k * 2.1 + i)) * math.cos(2 * PI * k / sides + seed * 0.3 + i * 0.25),
                                 rr * (1 + 0.25 * math.cos(seed + k * 1.7 + i)) * math.sin(2 * PI * k / sides + seed * 0.3 + i * 0.25),
                                 0)) for k in range(sides)])
    cen = [sum(rw, Vector()) / sides for rw in rows]
    mb.grid(rows, mat, closed_u=True, smooth=False, want=lambda i, j: rows[i][j] - cen[i])
    tip = Vector(base) + Vector((bend_v[0] * h, bend_v[1] * h, h))
    ti = mb.v(tip)
    ids = [mb.v(p) for p in rows[-1]]
    for k in range(sides):
        mb.face([ids[k], ids[(k + 1) % sides], ti], [(0, 0), (0.4, 0), (0.2, 0.6)], mat, False, rows[-1][k] - cen[-1])


def build_obsidian_spires(variant=0):
    mb = MB(f"SM_ObsidianSpires_{'AB'[variant]}")
    count = 7 if variant == 0 else 4
    hmax = 14.0 if variant == 0 else 8.0
    for k in range(count):
        a = 2 * PI * k / count + rng.uniform(-0.3, 0.3)
        r = 0 if k == 0 else rng.uniform(1.2, 3.2)
        h = hmax if k == 0 else hmax * rng.uniform(0.35, 0.75)
        lean = (math.cos(a) * 0.12 * (r > 0), math.sin(a) * 0.12 * (r > 0))
        spire(mb, V(r * math.cos(a), r * math.sin(a), 0), h, hmax * 0.11 * (h / hmax) ** 0.6 + 0.3, seed=k * 1.3 + variant,
              sides=5 + (k % 2), bend_v=lean)
    rock(mb, V(0, 0, 0), (6.5, 6.0, 1.6), "M_LavaRock", seed=81 + variant, sub=2, amp=0.3, flat=0.3)
    return mb


def build_crystal_cluster():
    mb = MB("SM_EmberCrystals")
    rock(mb, V(0, 0, 0), (2.6, 2.3, 0.9), "M_LavaRock", seed=91, sub=2, amp=0.3, flat=0.3)
    for k in range(11):
        a = rng.uniform(0, 2 * PI)
        r = rng.uniform(0, 0.9) if k else 0
        h = rng.uniform(0.7, 2.8) if k else 3.2
        rad = 0.08 + 0.12 * h / 2.8
        tilt = V(math.cos(a), math.sin(a), 0) * (0.15 + 0.5 * r) if k else V(0, 0, 0)
        base = V(r * math.cos(a), r * math.sin(a), 0.3)
        axis = (V(0, 0, 1) + tilt).normalized()
        sd = axis.orthogonal().normalized()
        u2 = axis.cross(sd)
        seg = 6
        rows = []
        for f in (0.0, 0.78):
            c = base + axis * (h * f)
            rows.append([c + sd * (rad * math.cos(2 * PI * j / seg)) + u2 * (rad * math.sin(2 * PI * j / seg)) for j in range(seg)])
        ids = [[mb.v(p) for p in rw] for rw in rows]
        tip = mb.v(base + axis * h)
        for j in range(seg):
            j1 = (j + 1) % seg
            u0, u1 = j / seg, (j + 1) / seg
            mb.face([ids[0][j], ids[0][j1], ids[1][j1], ids[1][j]], [(u0, 0), (u1, 0), (u1, 0.78), (u0, 0.78)], "M_Crystal",
                    False, rows[0][j] - base)
            mb.face([ids[1][j], ids[1][j1], tip], [(u0, 0.78), (u1, 0.78), ((u0 + u1) / 2, 1.0)], "M_Crystal", False,
                    rows[1][j] - (base + axis * h * 0.78))
    return mb


def build_lava_rock(i):
    mb = MB(f"SM_LavaRock_{'ABC'[i]}")
    sizes = [(3.0, 2.4, 1.8), (1.6, 1.4, 1.0), (5.0, 3.2, 2.2)]
    rock(mb, V(0, 0, 0), sizes[i], "M_LavaRock", seed=101 + i, sub=3, amp=0.42, freq=1.5, flat=0.2, rotz=0.0)
    return mb


# =========================================================================== 4. WATERFALL
FALL_H = 24.0
FALL_W = 4.5


def build_falls_lip():
    """Rock lip the water pours over. Flow travels +X; the channel crest is at (LIP_X, 0, LIP_Z)."""
    mb = MB("SM_FallsLip")

    def warp(q):
        ch = math.exp(-(q.y / 2.6) ** 2)
        if q.z > 0:
            q = Vector((q.x, q.y, q.z - 1.6 * ch * min(1.0, q.z / 2.0)))
        return q
    rock(mb, V(0, 0, 0), (12, 16, 7), "M_Rock", seed=121, sub=4, amp=0.22, freq=0.9, flat=0.1, rotz=0.0, warp=warp)
    return mb


def build_waterfall_sheet():
    """Falling-water sheet. Origin at its base centre; the top edge attaches to the lip crest (manifest).
    UV: U 0..1 across, V = metres from the bottom / 4 (tiles). Pan +V to flow downward."""
    mb = MB("SM_WaterfallSheet")
    nu, nv = 9, 30
    rows = []
    for i in range(nv + 1):
        f = i / nv                          # 0 = top of fall .. 1 = bottom
        drop = FALL_H * f
        x = 0.62 * math.sqrt(drop) - 1.0 * (1 - min(1.0, f * 12))
        z = FALL_H - drop
        if i == 0:
            x, z = -1.4, FALL_H + 0.15
        w = FALL_W * (1 + 0.35 * f)
        row = []
        for j in range(nu):
            u = j / (nu - 1)
            y = (u - 0.5) * w
            row.append(V(x + 0.15 * math.sin(u * 7 + f * 9) * f + 0.25 * (1 - abs(2 * u - 1)) * min(1, f * 6),
                         y, z))
        rows.append(row)
    xb = rows[-1][nu // 2].x
    rows = [[p - V(xb, 0, 0) for p in r] for r in rows]
    arc = [0.0]
    for i in range(1, nv + 1):
        arc.append(arc[-1] + (rows[i][nu // 2] - rows[i - 1][nu // 2]).length)
    total = arc[-1]
    mb.grid(rows, "M_Waterfall", uv=lambda i, j: (j / (nu - 1), (total - arc[i]) / 4.0), want=(1, 0, 0))
    top = rows[0][nu // 2]
    return mb, (round(top.x, 3), 0.0, round(top.z, 3))


def build_waterfall_foam():
    """Foam + mist cards for the plunge point: 3 crossed vertical cards + a floating foam ring. Origin = water level."""
    mb = MB("SM_WaterfallFoam")
    for k in range(3):
        a = PI * k / 3
        d = V(math.cos(a), math.sin(a), 0)
        w, h = 9.0, 6.0
        p = [-d * w / 2 + V(0, 0, -0.5), d * w / 2 + V(0, 0, -0.5), d * w / 2 + V(0, 0, h), -d * w / 2 + V(0, 0, h)]
        mb.face([mb.v(q) for q in p], [(0, 0), (2, 0), (2, 1), (0, 1)], "M_Foam", True, V(-d.y, d.x, 0))
    ns = 16
    rows = []
    for r, z in ((1.0, 0.05), (4.0, 0.05), (7.5, 0.03)):
        rows.append([V(r * math.cos(2 * PI * k / ns), r * math.sin(2 * PI * k / ns), z) for k in range(ns)])
    mb.grid(rows, "M_Foam", closed_u=True, uv=lambda i, j: (j / ns * 3, 0.3 + 0.2 * i), want=(0, 0, 1))
    return mb


def build_plunge_rocks():
    mb = MB("SM_PlungeRocks")
    for k in range(9):
        a = 2 * PI * k / 9 + 0.35
        if abs(math.cos(a) - 1) < 0.25:
            continue   # leave the outflow (+X) open
        r = rng.uniform(7.0, 9.0)
        s = rng.uniform(2.2, 4.2)
        rock(mb, V(r * math.cos(a), r * math.sin(a), -0.8), (s * 1.3, s, s * 0.8), "M_Rock", seed=130 + k, sub=2, amp=0.3)
    for k in range(5):
        a = rng.uniform(0, 2 * PI)
        r = rng.uniform(3, 6)
        rock(mb, V(r * math.cos(a), r * math.sin(a), -0.6), (1.4, 1.1, 1.0), "M_Rock", seed=150 + k, sub=1, amp=0.3)
    return mb


# =========================================================================== 5. COASTAL DRESSING
def build_wreck(bow=True):
    """Half a broken longship, lying heeled over in the sand. Built from the kit hull surface."""
    mb = MB("SM_WreckBow" if bow else "SM_WreckStern")
    sgn = 1 if bow else -1
    N = 16
    lap = 0.05
    ts_all = [K.T_END * math.sin(PI / 2 * (k / 30)) for k in range(31)]
    for side in (1, -1):
        for i in range(N):
            if i > 5 and rng.random() < 0.18:
                continue
            tb = rng.uniform(0.04, 0.3)
            ts = [t for t in ts_all if t >= tb]
            if len(ts) < 2:
                continue
            st, sb = (i + 1) / N, max(0.0, i / N - 0.012)
            rows, wants = [], []
            for t in ts:
                tt = sgn * t
                top = K.mir(K.hp(tt, st), side)
                bot = K.mir(K.hp(tt, sb), side)
                nb = K.hn(tt, sb, side)
                rows.append([bot, bot + nb * lap, top])
                wants.append(((bot - top).normalized() + nb * 0.4, K.hn(tt, (sb + st) / 2, side)))
            mb.grid(rows, "M_WoodTar", want=lambda r, c, w=wants: w[r][c])
        ts = [t for t in ts_all if t >= 0.35]
        rows = [[K.mir(K.hp(sgn * t, s), side) - K.hn(sgn * t, s, side) * 0.04 for s in [k / 8 for k in range(9)]] for t in ts]
        mb.grid(rows, "M_Wood", want=lambda r, c, ts=ts: -K.hn(sgn * ts[r], 0.5, side))
    for k in range(9):
        t = 0.06 + 0.7 * k / 8
        for side in (1, -1):
            pts = [K.mir(K.hp(sgn * t, s), side) - K.hn(sgn * t, s, side) * 0.07 for s in [0.05 + 0.92 * j / 6 for j in range(7)]]
            mb.tube(pts, RECT, (0.035, 0.05), "M_Wood", side=(1, 0, 0), cap0=True, cap1=True)
    keel = [K.hp(sgn * t, 0) for t in ts_all if t > 0.02]
    mb.tube(keel, [(-0.07, -0.24), (0.07, -0.24), (0.07, 0.04), (-0.07, 0.04)], 1.0, "M_WoodTar", side=(0, 1, 0))
    stem = [K.hp(sgn * K.T_END, s / 10) + V(sgn * 0.06, 0, 0) for s in range(11)]
    stem += [stem[-1] + V(sgn * 0.1, 0, 0.5), stem[-1] + V(sgn * 0.14, 0, 0.9)]
    mb.tube(stem, ellipse(10, 2.4), [(0.09, 0.14)] * len(stem), "M_WoodTar", side=(0, 1, 0), cap1=True)
    # heel over and bury
    M = Matrix.Rotation(math.radians(24), 3, "X") @ Matrix.Rotation(math.radians(-4 * sgn), 3, "Y")
    transform(mb, 0, M)
    xs = [v[0] for v in mb.V]
    cx = (min(xs) + max(xs)) / 2
    zmin = min(v[2] for v in mb.V)
    mb.V = [(x - cx, y, z - zmin - 0.6) for x, y, z in mb.V]
    return mb


def build_beacon():
    """Viking beacon tower: dry-stone round tower, timber crown, iron fire basket (attach 'fire')."""
    mb = MB("SM_BeaconTower")
    seg = 20
    H = 9.0
    rows = []
    for k in range(7):
        f = k / 6
        z = -0.3 + (H + 0.3) * f
        r = 2.7 - 0.6 * f + 0.08 * math.sin(f * PI)
        rows.append([V(r * math.cos(2 * PI * j / seg), r * math.sin(2 * PI * j / seg), z) for j in range(seg)])
    mb.grid(rows, "M_Stone", closed_u=True, want=lambda i, j: rows[i][j] - V(0, 0, rows[i][j].z))
    mb.cap(rows[-1], "M_Stone", (0, 0, 1))
    # door
    mb.box((2.62, 0, 1.0), (0.2, 1.1, 2.0), "M_Wood")
    mb.box((2.7, 0, 2.1), (0.4, 1.6, 0.3), "M_Stone")
    for z in (0.5, 1.5):
        mb.box((2.74, 0, z), (0.03, 1.0, 0.08), "M_Iron")
    # timber crown
    mb.cyl((0, 0, H), (0, 0, H + 0.25), 2.55, seg=16, mat="M_WoodTar")
    for j in range(16):
        a = 2 * PI * j / 16
        mb.cyl((2.35 * math.cos(a), 2.35 * math.sin(a), H + 0.2), (2.35 * math.cos(a), 2.35 * math.sin(a), H + 1.4), 0.09,
               seg=5, mat="M_Wood")
    ring = [V(2.35 * math.cos(2 * PI * j / 16), 2.35 * math.sin(2 * PI * j / 16), H + 1.1) for j in range(17)]
    mb.tube(ring, RECT, (0.06, 0.08), "M_Wood", side=(0, 0, 1))
    # iron fire basket on a plinth
    mb.cyl((0, 0, H + 0.25), (0, 0, H + 1.0), 0.6, 0.5, seg=8, mat="M_Stone")
    for j in range(10):
        a = 2 * PI * j / 10
        mb.cyl((0.5 * math.cos(a), 0.5 * math.sin(a), H + 1.0), (1.0 * math.cos(a), 1.0 * math.sin(a), H + 2.3), 0.04, seg=4,
               mat="M_Iron")
    for rr, z in ((0.55, H + 1.1), (1.0, H + 2.3), (0.78, H + 1.7)):
        ring = [V(rr * math.cos(2 * PI * j / 12), rr * math.sin(2 * PI * j / 12), z) for j in range(13)]
        mb.tube(ring, RECT, (0.03, 0.05), "M_Iron", side=(0, 0, 1))
    for k in range(9):
        a = rng.uniform(0, 2 * PI)
        z = H + 1.2 + rng.uniform(0, 0.8)
        d = V(math.cos(a), math.sin(a), rng.uniform(-0.3, 0.3))
        mb.cyl(V(0, 0, z) - d * 0.75, V(0, 0, z) + d * 0.75, 0.12, seg=6, mat="M_Charred")
    # ladder up the side
    for sy in (-0.3, 0.3):
        mb.box((-2.75, sy, H / 2), (0.08, 0.08, H + 1.5), "M_Wood", rot=(0, math.atan2(0.4, H), 0))
    for k in range(22):
        z = 0.3 + (H - 0.2) * k / 21
        mb.box((-2.75 - (H / 2 - z) * 0.4 / H, 0, z), (0.05, 0.6, 0.05), "M_Wood")
    return mb, (0.0, 0.0, H + 1.5)


def driftlog(mb, base, length, r, seed, ang):
    d = V(math.cos(ang), math.sin(ang), 0)
    side = V(-d.y, d.x, 0)
    pts = []
    for k in range(6):
        f = k / 5
        p = Vector(base) + d * (length * (f - 0.5)) + side * (0.4 * math.sin(f * 3 + seed)) + V(0, 0, r + 0.1 * math.sin(f * 4 + seed))
        pts.append(p)
    mb.tube(pts, ellipse(7), [r * (1.25 - 0.5 * f) for f in [k / 5 for k in range(6)]], "M_Wood", side=(0, 0, 1),
            cap0=True, cap1=True)
    for k in range(rng.randint(1, 3)):
        p = pts[rng.randint(1, 4)]
        bd = (side * rng.choice((-1, 1)) + V(0, 0, rng.uniform(0.2, 0.9)) + d * rng.uniform(-0.5, 0.5)).normalized()
        mb.cone(p, p + bd * rng.uniform(0.5, 1.3), r * 0.45, seg=5, mat="M_Wood")
    if rng.random() < 0.5:   # root flare
        p = pts[0]
        for k in range(5):
            a = 2 * PI * k / 5 + seed
            mb.cone(p, p + (-d * 0.6 + V(0, math.cos(a), math.sin(a)) * 0.8) * r * 3, r * 0.4, seg=4, mat="M_Wood")


def build_driftwood():
    mb = MB("SM_DriftwoodPile")
    for k in range(9):
        a = rng.uniform(-0.6, 0.6) + (PI / 2 if k % 3 == 0 else 0)
        base = V(rng.uniform(-1.5, 1.5), rng.uniform(-1.0, 1.0), 0.35 * (k // 3))
        driftlog(mb, base, rng.uniform(2.5, 5.5), rng.uniform(0.1, 0.24), k * 1.1, a)
    return mb
