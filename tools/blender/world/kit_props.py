"""Procedural geometry for every prop in the Viking village + fleet kit.

Each builder returns MB (mesh builder) instances; build_props.py turns them into
objects, assigns the shared kit materials and exports them.
Units: metres. Origin at base centre (ship: waterline centre). +X forward.
"""
import math

from mathutils import Euler, Matrix, Vector

from kit_geo import MB, V, rng

PI = math.pi


def ellipse(seg, p=2.0):
    out = []
    for k in range(seg):
        a = 2 * PI * k / seg
        c, s = math.cos(a), math.sin(a)
        out.append((math.copysign(abs(c) ** (2 / p), c), math.copysign(abs(s) ** (2 / p), s)))
    return out


RECT = [(-1, -1), (1, -1), (1, 1), (-1, 1)]


# =========================================================================== LONGSHIP
HL = 10.0          # half hull length at the gunwale ends
T_END = 0.997


def hp(t, s):
    """Hull outer surface point (port side, +Y). t: -1 stern .. +1 bow, s: 0 keel .. 1 gunwale."""
    a = min(abs(t), 1.0)
    hb = 2.55 * max(0.0, 1 - a ** 2.3) ** 0.7
    zk = -0.85 + 0.6 * a ** 2.6
    zs = 1.15 + 2.2 * a ** 3.6
    bl = a ** 2
    Y = (1 - bl) * math.sin(s * PI / 2) ** 0.85 + bl * s
    Z = (1 - bl) * (0.8 * (1 - math.cos(s * PI / 2)) + 0.2 * s) + bl * s ** 1.5
    x = math.copysign(HL * a * (1 - 0.18 * (1 - s) ** 2.2 * a ** 3), t)
    return Vector((x, hb * Y, zk + (zs - zk) * Z))


def hn(t, s, side=1):
    d = 1e-3
    pt = hp(min(t + d, 1), s) - hp(max(t - d, -1), s)
    ps = hp(t, min(s + d, 1)) - hp(t, max(s - d, 0))
    n = pt.cross(ps)
    if n.length < 1e-9:
        n = Vector((0, 1, 0))
    n.normalize()
    if n.y < 0:
        n = -n
    if side < 0:
        n = Vector((n.x, -n.y, n.z))
    return n


def mir(p, side):
    return Vector((p.x, p.y * side, p.z))


def t_at_x(x, s):
    lo, hi = 0.0, 1.0
    for _ in range(40):
        m = (lo + hi) / 2
        if hp(m, s).x < abs(x):
            lo = m
        else:
            hi = m
    return math.copysign((lo + hi) / 2, x)


def s_at_z(t, z):
    lo, hi = 0.0, 1.0
    for _ in range(40):
        m = (lo + hi) / 2
        if hp(t, m).z < z:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


OAR_X = [-6.6 + 13.2 * k / 15 for k in range(16)]
OAR_S = 0.86
SHIELD_X = [-6.85 + 13.7 * k / 31 for k in range(32)]
MAST_X = 0.4
YARD = Vector((MAST_X + 0.25, 0.0, 10.5))   # sail attach point (yard centre)


def build_longship():
    mb = MB("SM_Longship")
    ts = [T_END * math.sin(PI / 2 * (-1 + 2 * k / 60)) for k in range(61)]
    N = 16
    lap = 0.05
    # ---------------- clinker strakes (outer), both sides
    for side in (1, -1):
        for i in range(N):
            st = (i + 1) / N
            sb = max(0.0, i / N - 0.012)
            rows = []
            wants = []
            for t in ts:
                top = mir(hp(t, st), side)
                bot = mir(hp(t, sb), side)
                nb = hn(t, sb, side)
                rows.append([bot, bot + nb * lap, top])
                wants.append(((bot - top).normalized() + nb * 0.4, hn(t, (sb + st) / 2, side)))
            mb.grid(rows, "M_WoodTar", want=lambda r, c, w=wants: w[r][c])
        # inner skin (lighter, untarred interior)
        rows = []
        wants = []
        for t in ts:
            rows.append([mir(hp(t, s), side) - hn(t, s, side) * 0.04 for s in [k / 9 for k in range(10)]])
            wants.append(-hn(t, 0.5, side))
        mb.grid(rows, "M_Wood", want=lambda r, c, w=wants: w[r])
        # gunwale cap + rail
        rows = [[mir(hp(t, 1), side), mir(hp(t, 1), side) - hn(t, 1, side) * 0.04] for t in ts]
        mb.grid(rows, "M_WoodTar", want=(0, 0, 1))
        rail = [mir(hp(t, 1), side) + hn(t, 1, side) * 0.01 + V(0, 0, 0.03) for t in ts[2:-2]]
        mb.tube(rail, RECT, (0.06, 0.045), "M_WoodTar", side=(0, 0, 1), cap0=True, cap1=True)

    # ---------------- keel
    keel = [hp(t, 0) for t in ts[1:-1]]
    mb.tube(keel, [(-0.07, -0.24), (0.07, -0.24), (0.07, 0.04), (-0.07, 0.04)], 1.0, "M_WoodTar", side=(0, 1, 0))

    # ---------------- stem (bow) with dragon neck + head
    stem = [hp(T_END, s / 10) + V(0.06, 0, 0) for s in range(11)]
    top = stem[-1]
    neck = [top + V(dx, 0, dz) for dx, dz in ((0.10, 0.45), (0.12, 0.9), (0.18, 1.3), (0.32, 1.62), (0.52, 1.82), (0.72, 1.9))]
    path = stem + neck
    sc = []
    for i in range(len(path)):
        f = i / (len(path) - 1)
        sc.append((0.09 + 0.075 * f ** 1.5, 0.14 + 0.085 * f ** 1.5))
    mb.tube(path, ellipse(12, 2.4), sc, "M_WoodTar", side=(0, 1, 0))
    head_base = neck[-1]
    n0 = len(mb.V)
    build_dragon_head(mb, head_base, pitch=-6.0)
    HS = 1.4   # head scale
    for i in range(n0, len(mb.V)):
        q = Vector(mb.V[i])
        mb.V[i] = tuple(head_base + (q - head_base) * HS)
    # dorsal spikes on the back of the neck
    for k in range(2, len(neck)):
        p = neck[k - 1]
        tdir = (neck[k] - neck[k - 2]).normalized()
        back = tdir.cross(V(0, 1, 0)).normalized()  # rearward/up side of the curve
        if back.x > 0:
            back = -back
        mb.cone(p + back * 0.16, p + back * 0.45 + tdir * -0.12, 0.075, seg=4, mat="M_WoodTar")

    # ---------------- stern post with spiral
    stern = [hp(-T_END, s / 10) + V(-0.06, 0, 0) for s in range(11)]
    s0 = stern[-1]
    c = s0 + V(0, 0, 0.95)
    spiral = []
    for k in range(1, 30):
        th = math.radians(330 * k / 29)
        phi = -PI / 2 - th
        r = 0.95 * (1 - 0.62 * th / math.radians(330))
        spiral.append(c + V(r * math.cos(phi), 0, r * math.sin(phi)))
    path = stern + spiral
    sc = []
    for i in range(len(path)):
        f = i / (len(path) - 1)
        sc.append((0.085 - 0.04 * f, 0.13 - 0.07 * f))
    mb.tube(path, ellipse(12, 2.4), sc, "M_WoodTar", side=(0, 1, 0), cap1=True)

    # ---------------- interior: floor, ribs, cross beams, sea chests
    zf = -0.38
    tf = [-0.78 + 1.56 * k / 24 for k in range(25)]
    hw = []
    for t in tf:
        s = s_at_z(t, zf)
        p = hp(t, s)
        hw.append((p.x, max(0.05, p.y - 0.06)))
    nb = 10
    for b in range(nb):
        dz = rng.uniform(-0.008, 0.008)
        rows = []
        for x, w in hw:
            y0 = -w + 2 * w * (b + 0.03) / nb
            y1 = -w + 2 * w * (b + 0.97) / nb
            rows.append([V(x, y0, zf + dz), V(x, y1, zf + dz)])
        mb.grid(rows, "M_Wood", want=(0, 0, 1))
    for k in range(17):
        t = -0.8 + 1.6 * k / 16
        sf = s_at_z(t, zf - 0.05)
        for side in (1, -1):
            pts = [mir(hp(t, s), side) - hn(t, s, side) * 0.07 for s in [sf + (0.97 - sf) * j / 6 for j in range(7)]]
            mb.tube(pts, RECT, (0.03, 0.045), "M_Wood", side=(1, 0, 0), cap1=True)
        sb_ = 0.6
        pz = hp(t, sb_)
        mb.box((pz.x, 0, pz.z), (0.12, 2 * (pz.y - 0.08), 0.13), "M_Wood")
    for x in OAR_X:
        t = t_at_x(x, 0.3)
        p = hp(t, s_at_z(t, zf + 0.3))
        for side in (1, -1):
            mb.box((x, side * (p.y - 0.42), zf + 0.2), (0.7, 0.42, 0.4), "M_Wood", rot=(0, 0, rng.uniform(-0.04, 0.04)))

    # ---------------- mast, mast fish, yard, rigging
    mb.tube([V(MAST_X - 1.7 + 3.4 * k / 4, 0, zf + 0.02 + 0.32 * math.sin(PI * k / 4)) for k in range(5)],
            RECT, [(0.2, 0.08), (0.22, 0.2), (0.24, 0.28), (0.22, 0.2), (0.2, 0.08)], "M_Wood", side=(0, 1, 0),
            cap0=True, cap1=True)
    mb.cyl((MAST_X, 0, -0.6), (MAST_X, 0, 11.9), 0.17, 0.09, seg=10, mat="M_Wood", rings=4)
    yard = [V(YARD.x, -5.9 + 11.8 * k / 8, YARD.z) for k in range(9)]
    mb.tube(yard, ellipse(8), [0.05 + 0.06 * math.sin(PI * k / 8) for k in range(9)], "M_Wood",
            side=(0, 0, 1), cap0=True, cap1=True)
    mast_top = V(MAST_X, 0, 11.7)

    def rope(a, b, r=0.022):
        mb.cyl(a, b, r, seg=4, mat="M_WoodTar", cap0=False, cap1=False)
    rope(mast_top, hp(T_END, 1) + V(0.1, 0, 0.3))
    rope(mast_top, hp(-T_END, 1) + V(-0.1, 0, 0.4))
    for side in (1, -1):
        for x in (-0.6, -1.5, -2.4):
            t = t_at_x(x, 1)
            rope(V(MAST_X, 0, 11.2), mir(hp(t, 1), side) + V(0, 0, 0.05))

    # ---------------- shields along both gunwales (alternating offset, cells 0..15 of atlas)
    for side in (1, -1):
        for k, x in enumerate(SHIELD_X):
            t = t_at_x(x, 1)
            p = mir(hp(t, 1), side)
            n = hn(t, 1, side)
            nh = V(n.x, n.y, 0).normalized()
            cen = p + V(0, 0, 0.2) + nh * (0.085 + 0.022 * (k % 2))
            cell = (k * 5 + (3 if side < 0 else 0)) % 16
            build_shield(mb, cen, nh, cell)

    # ---------------- steering oar (starboard = -Y) near the stern
    t = t_at_x(-8.3, 0.8)
    piv = mir(hp(t, 0.8), -1) + hn(t, 0.8, -1) * 0.18
    top_ = piv + V(0.15, 0, 1.3)
    bot_ = piv + V(-0.45, 0, -1.6)
    mb.cyl(top_, bot_, 0.09, 0.07, seg=8, mat="M_Wood")
    d = (bot_ - top_).normalized()
    mid = piv.lerp(bot_, 0.55)
    blade_rot = Matrix.Rotation(math.atan2(d.x, -d.z), 3, "Y")
    mb.box(mid + V(-0.18, 0, 0), (0.5, 0.08, 1.9), "M_Wood", rot=blade_rot)
    mb.box(top_ + V(0, 0.65, -0.05), (0.08, 1.3, 0.08), "M_Wood")
    mb.box(piv + V(0, 0.12, 0), (0.25, 0.25, 0.35), "M_WoodTar")   # rudder boss
    return mb


def build_dragon_head(mb, base, pitch=-6.0, eyes=True):
    """Carved dragon head on the stem. Local frame: +X snout, +Z up; base at the neck end."""
    R = Matrix.Rotation(math.radians(pitch), 3, "Y")

    def W(p):
        return base + R @ Vector(p)

    def ring(x, wy, zc, hz, seg=14, p=2.6, d=None, up=None):
        out = []
        for (cy, cz) in ellipse(seg, p):
            if d is None:
                out.append(W((x, cy * wy, zc + cz * hz)))
            else:
                out.append(W(Vector(d[0]) + Vector(d[1]) * 0 + Vector((0, cy * wy, 0)) + Vector(up) * (cz * hz)))
        return out

    def loft(secs, mat="M_WoodTar", capend=True):
        rows = [ring(*s) for s in secs]
        cen = [W((s[0], 0, s[2])) for s in secs]
        mb.grid(rows, mat, closed_u=True, want=lambda i, j: rows[i][j] - cen[i])
        if capend:
            mb.cap(rows[-1], mat, R @ Vector((1, 0, 0)))

    # skull
    loft([(-0.18, 0.11, 0.0, 0.17), (0.0, 0.15, 0.03, 0.2), (0.15, 0.17, 0.05, 0.21), (0.3, 0.17, 0.04, 0.19),
          (0.45, 0.15, 0.03, 0.16), (0.56, 0.13, 0.03, 0.13)])
    # upper jaw / snout (z top, z bottom -> centre, half height)
    up = [(0.40, 0.14, 0.17, -0.03), (0.6, 0.125, 0.13, -0.01), (0.8, 0.105, 0.105, 0.0), (0.98, 0.09, 0.10, 0.01),
          (1.1, 0.075, 0.125, 0.03), (1.18, 0.05, 0.13, 0.07)]
    loft([(x, wy, (zt + zb) / 2, (zt - zb) / 2) for x, wy, zt, zb in up])
    # nostril curls
    for sgn in (1, -1):
        mb.tube([W((1.02, sgn * 0.06, 0.13)), W((1.1, sgn * 0.08, 0.2)), W((1.06, sgn * 0.1, 0.27)), W((0.99, sgn * 0.09, 0.25))],
                ellipse(6), [0.035, 0.03, 0.022, 0.015], "M_WoodTar", side=(0, 1, 0), cap1=True)
    # lower jaw, hinged open 24 degrees
    ang = math.radians(24)
    hinge = Vector((0.40, 0, -0.06))
    dj = Vector((math.cos(ang), 0, -math.sin(ang)))
    uj = Vector((math.sin(ang), 0, math.cos(ang)))
    rows, cen = [], []
    for q, wy, hz in ((0.0, 0.13, 0.075), (0.25, 0.115, 0.065), (0.5, 0.095, 0.055), (0.68, 0.075, 0.045), (0.78, 0.05, 0.035)):
        c = hinge + dj * q
        cen.append(W(c))
        rows.append([W(c + Vector((0, cy * wy, 0)) + uj * (cz * hz)) for cy, cz in ellipse(12, 2.6)])
    mb.grid(rows, "M_WoodTar", closed_u=True, want=lambda i, j: rows[i][j] - cen[i])
    mb.cap(rows[-1], "M_WoodTar", R @ dj)
    # teeth
    for sgn in (1, -1):
        for x in (0.55, 0.68, 0.81, 0.93, 1.04):
            wy = 0.14 - (x - 0.4) * 0.09
            zb = -0.03 + (x - 0.4) * 0.07
            mb.cone(W((x, sgn * wy * 0.75, zb + 0.01)), W((x + 0.01, sgn * wy * 0.72, zb - 0.075)), 0.018, seg=4, mat="M_Wood")
        for q in (0.2, 0.35, 0.5, 0.63):
            wy = 0.13 - q * 0.1
            b = hinge + dj * q + uj * 0.04
            mb.cone(W(b + Vector((0, sgn * wy * 0.72, 0))), W(b + Vector((0, sgn * wy * 0.7, 0)) + uj * 0.07), 0.016, seg=4, mat="M_Wood")
    # tongue
    mb.tube([W((0.42, 0, -0.05)), W((0.68, 0, -0.12)), W((0.92, 0, -0.16)), W((1.08, 0, -0.08)), W((1.13, 0, 0.0))],
            ellipse(6), [(0.045, 0.02), (0.04, 0.018), (0.035, 0.016), (0.025, 0.012), (0.012, 0.008)], "M_WoodTar",
            side=(0, 1, 0), cap1=True)
    # eyes + brows
    for sgn in (1, -1):
        if eyes:
            mb.sphere(W((0.27, sgn * 0.155, 0.12)), 0.055, "M_Wood", seg=8, rings=5, scale=(1.3, 0.85, 1.0))
        mb.tube([W((0.14, sgn * 0.14, 0.18)), W((0.27, sgn * 0.175, 0.215)), W((0.4, sgn * 0.15, 0.17))],
                ellipse(6), [0.03, 0.034, 0.022], "M_WoodTar", side=(0, 1, 0), cap0=True, cap1=True)
    # curled horns
    for sgn in (1, -1):
        pts = [(0.06, 0.10, 0.18), (-0.08, 0.16, 0.33), (-0.3, 0.21, 0.42), (-0.52, 0.22, 0.36), (-0.62, 0.2, 0.22),
               (-0.56, 0.18, 0.12)]
        mb.tube([W((x, sgn * y, z)) for x, y, z in pts], ellipse(7), [0.075, 0.066, 0.054, 0.04, 0.028, 0.014],
                "M_WoodTar", side=(0, 0, 1), cap1=True, transport=True)


SHIELD_R = 0.46


def build_shield(mb, cen, nrm, cell, seg=14):
    up = V(0, 0, 1)
    up = (up - nrm * up.dot(nrm)).normalized()
    rt = up.cross(nrm)
    ci, cj = cell % 4, cell // 4

    def P(r, z, a):
        return cen + rt * (r * math.cos(a)) + up * (r * math.sin(a)) + nrm * z

    def UVa(r, a):
        rr = r / SHIELD_R * 0.96 * 0.5
        return ((ci + 0.5 + rr * math.cos(a)) / 4, (cj + 0.5 + rr * math.sin(a)) / 4)
    angs = [2 * PI * k / seg for k in range(seg)]
    rings = [(SHIELD_R, 0.0), (0.3, 0.018), (0.1, 0.03)]
    ids = [[mb.v(P(r, z, a)) for a in angs] for r, z in rings]
    for i in range(len(rings) - 1):
        for k in range(seg):
            k1 = (k + 1) % seg
            q = [ids[i][k], ids[i][k1], ids[i + 1][k1], ids[i + 1][k]]
            uv = [UVa(rings[i][0], angs[k]), UVa(rings[i][0], angs[k1] if k1 else 2 * PI),
                  UVa(rings[i + 1][0], angs[k1] if k1 else 2 * PI), UVa(rings[i + 1][0], angs[k])]
            mb.face(q, uv, "M_Shields", True, nrm)
    # boss (iron dome)
    br = [(0.1, 0.03), (0.075, 0.09)]
    bid = [[mb.v(P(r, z, a)) for a in angs] for r, z in br]
    apex = mb.v(cen + nrm * 0.13)
    for k in range(seg):
        k1 = (k + 1) % seg
        uvs = [(k / seg, 0), ((k + 1) / seg, 0), ((k + 1) / seg, 0.05), (k / seg, 0.05)]
        mb.face([bid[0][k], bid[0][k1], bid[1][k1], bid[1][k]], uvs, "M_Iron", True, nrm)
        mb.face([bid[1][k], bid[1][k1], apex], uvs[:3], "M_Iron", True, nrm)
    # rim edge (rawhide) to the back
    back = [mb.v(P(SHIELD_R * 0.98, -0.025, a)) for a in angs]
    for k in range(seg):
        k1 = (k + 1) % seg
        uvs = [UVa(SHIELD_R, angs[k])] * 2 + [UVa(SHIELD_R, angs[k1] if k1 else 2 * PI)] * 2
        mb.face([ids[0][k], back[k], back[k1], ids[0][k1]], uvs, "M_Shields", True,
                rt * math.cos(angs[k] + PI / seg) + up * math.sin(angs[k] + PI / seg))


def build_sail():
    """Sail in local space of the yard attach point; u across (+Y..-Y), v bottom..top."""
    mb = MB("SM_LongshipSail")
    nu, nv = 18, 14
    rows = []
    for i in range(nv):
        v = i / (nv - 1)
        row = []
        for j in range(nu):
            u = j / (nu - 1)
            half = 5.4 - 0.45 * (1 - v)
            y = (0.5 - u) * 2 * half
            z = -0.12 - (1 - v) * 8.55 + 0.25 * math.sin(PI * u) * (1 - v) ** 3
            bel = (1 - v ** 4) * (0.35 + 0.65 * math.sin(PI * v))
            x = 1.35 * math.sin(PI * u) ** 0.9 * bel + 0.05 * math.sin(PI * u * 3) * (1 - v)
            row.append(V(x, y, z))
        rows.append(row)
    mb.grid(rows, "M_Sail", uv=lambda i, j: (j / (nu - 1), i / (nv - 1)), want=(1, 0, 0))
    return mb


def build_oar():
    """Oar with its pivot (oar port) at the origin; blade outboard along +Y, handle along -Y."""
    mb = MB("SM_LongshipOar")
    sec = ellipse(6)
    mb.tube([V(0, -1.75, 0), V(0, -1.45, 0), V(0, 0, 0), V(0, 2.0, 0), V(0, 3.05, 0)], sec,
            [0.03, 0.042, 0.045, 0.04, 0.034], "M_Wood", side=(1, 0, 0), cap0=True)
    blade = [V(0, 2.95 + 1.1 * k / 4, 0) for k in range(5)]
    mb.tube(blade, RECT, [(0.012, 0.03), (0.016, 0.055), (0.016, 0.068), (0.015, 0.072), (0.012, 0.07)], "M_Wood",
            side=(1, 0, 0), cap1=True)
    return mb


def oar_pivots():
    out = []
    for side in (1, -1):
        for x in OAR_X:
            t = t_at_x(x, OAR_S)
            p = mir(hp(t, OAR_S), side) + hn(t, OAR_S, side) * 0.04
            rot = (math.radians(-12), 0.0, 0.0 if side > 0 else math.pi)
            out.append((p, rot, "Port" if side > 0 else "Starboard"))
    return out


# =========================================================================== TURF HOUSES
def turf_house(name, L, W, wall_h, ridge_h, bow=0.0, sag=0.0, eave_over=0.5, gable_over=0.35, th=0.42,
               buttress=0.0, base_z=0.0, doors=(), open_front=False, finials=True, smoke=None, sill=True, stilts=False):
    mb = MB(name)
    xe = L / 2 + gable_over

    def w(x):
        x = max(-L / 2, min(L / 2, x))
        return W / 2 * (1 - bow * (2 * x / L) ** 2)

    def ridge(x):
        return base_z + ridge_h - sag * (x / xe) ** 2

    s0 = (ridge_h - wall_h) / (W / 2)

    def eave(x):
        return base_z + wall_h - eave_over * s0 * 0.7

    def under(x, q, side):
        y = side * (w(x) + eave_over) * (1 - q)
        z = eave(x) + (ridge(x) - eave(x)) * (1 - (1 - q) ** 1.3)
        return V(x, y, z)

    def under_at_y(x, y):
        q = 1 - abs(y) / (w(x) + eave_over)
        return under(x, q, 1).z

    def lump(x, y):
        return (0.06 * math.sin(1.3 * x + 2.1 * y) + 0.045 * math.sin(2.9 * x - 1.7 * y + 1.0) +
                0.03 * math.sin(5.3 * x + 4.1 * y + 2.0) + 0.02 * math.sin(9.7 * x - 7.3 * y + 0.5))

    def top(x, q, side):
        p = under(x, q, side)
        d = 0.01
        a = under(x + d, q, side) - under(x - d, q, side)
        b = under(x, min(q + d, 1), side) - under(x, max(q - d, 0), side)
        n = a.cross(b).normalized()
        if n.z < 0:
            n = -n
        droop = -0.07 * (1 - q) ** 6
        return p + n * (th + lump(x, p.y) * (0.4 + 0.6 * q)) + V(0, 0, droop)

    nx = max(8, int(2 * xe / 0.75))
    xs = [-xe + 2 * xe * k / nx for k in range(nx + 1)]
    nq = 7
    qs = [k / nq for k in range(nq + 1)]
    for side in (1, -1):
        rows = [[top(x, q, side) for q in qs] for x in xs]
        mb.grid(rows, "M_Turf", want=(0, side * 0.5, 1))
        rows = [[under(x, q, side) for q in qs] for x in xs]
        mb.grid(rows, "M_Wood", want=(0, -side * 0.3, -1))
        rows = [[under(x, 0, side), top(x, 0, side)] for x in xs]
        mb.grid(rows, "M_Turf", want=(0, side, -0.3))
        for sx in (-1, 1):
            x = sx * xe
            rows = [[under(x, q, side), top(x, q, side)] for q in qs]
            mb.grid(rows, "M_Turf", want=(sx, 0, 0))

    # -------- walls
    def in_door(wall, a):
        for d in doors:
            if d[0] == wall and abs(a - d[1]) < d[2] / 2 + 0.02:
                return True
        return False
    z0 = base_z - (0.05 if not stilts else 0.12)
    nbx = max(4, int(L / 0.32))
    for side in (1, -1):
        wall = "+y" if side > 0 else "-y"
        if open_front and side > 0:
            continue
        for k in range(nbx):
            x0 = -L / 2 + L * k / nbx
            x1 = -L / 2 + L * (k + 1) / nbx
            xm = (x0 + x1) / 2
            if in_door(wall, xm):
                continue
            off = 0.03 if k % 2 else 0.0
            p = [V(x0, side * (w(x0) + off), z0), V(x1, side * (w(x1) + off), z0)]
            zt0 = under_at_y(x0, w(x0)) + 0.02
            zt1 = under_at_y(x1, w(x1)) + 0.02
            p += [V(x1, side * (w(x1) + off), zt1), V(x0, side * (w(x0) + off), zt0)]
            ids = [mb.v(q) for q in p]
            o = (rng.random(), rng.random())
            uv = [(o[0] + q.x / 2, o[1] + (q.z - z0) / 2) for q in p]
            uv = [(o[0] + (0 if i in (0, 3) else 0.16), o[1] + (p[i].z - z0) / 2) for i in range(4)]
            mb.face(ids, uv, "M_Wood", False, (0, side, 0))
            if off:
                for xx, zt, sg in ((x0, zt0, -1), (x1, zt1, 1)):
                    q = [V(xx, side * w(xx), z0), V(xx, side * (w(xx) + off), z0), V(xx, side * (w(xx) + off), zt),
                         V(xx, side * w(xx), zt)]
                    ids = [mb.v(a) for a in q]
                    mb.face(ids, [(0, 0), (0.015, 0), (0.015, 1), (0, 1)], "M_Wood", False, (sg, 0, 0))
    for sx in (-1, 1):
        wall = "+x" if sx > 0 else "-x"
        x = sx * L / 2
        ww = w(x)
        nby = max(3, int(2 * ww / 0.3))
        for k in range(nby):
            y0 = -ww + 2 * ww * k / nby
            y1 = -ww + 2 * ww * (k + 1) / nby
            if in_door(wall, (y0 + y1) / 2):
                continue
            off = 0.03 if k % 2 else 0.0
            xx = x + sx * off
            p = [V(xx, y0, z0), V(xx, y1, z0), V(xx, y1, under_at_y(x, y1) + 0.02), V(xx, y0, under_at_y(x, y0) + 0.02)]
            ids = [mb.v(q) for q in p]
            o = (rng.random(), rng.random())
            mb.face(ids, [(o[0], o[1]), (o[0] + 0.15, o[1]), (o[0] + 0.15, o[1] + (p[2].z - z0) / 2),
                          (o[0], o[1] + (p[3].z - z0) / 2)], "M_Wood", False, (sx, 0, 0))
            if off:
                for yy, sg in ((y0, -1), (y1, 1)):
                    zt = under_at_y(x, yy) + 0.02
                    q = [V(x, yy, z0), V(xx, yy, z0), V(xx, yy, zt), V(x, yy, zt)]
                    mb.face([mb.v(a) for a in q], [(0, 0), (0.015, 0), (0.015, 1), (0, 1)], "M_Wood", False, (0, sg, 0))
    # corner posts
    for sx in (-1, 1):
        for sy in (-1, 1):
            x = sx * L / 2
            mb.cyl((x, sy * w(x), z0), (x, sy * w(x), under_at_y(x, w(x))), 0.14, seg=7, mat="M_Wood")
    if open_front:
        n = max(2, int(L / 2.2))
        for k in range(1, n):
            x = -L / 2 + L * k / n
            mb.cyl((x, w(x), z0), (x, w(x), under_at_y(x, w(x))), 0.12, seg=7, mat="M_Wood")
        mb.box((0, w(0), base_z + wall_h - 0.1), (L, 0.18, 0.2), "M_Wood")
    # sloping outer posts (Trelleborg style)
    if buttress:
        n = int(L / buttress)
        for k in range(n + 1):
            x = -L / 2 + 0.6 + (L - 1.2) * k / n
            for side in (1, -1):
                if any(d[0] == ("+y" if side > 0 else "-y") and abs(x - d[1]) < d[2] / 2 + 0.4 for d in doors):
                    continue
                mb.cyl((x, side * (w(x) + 0.95), base_z - 0.1), (x, side * (w(x) + 0.12), base_z + wall_h - 0.2), 0.11, 0.1,
                       seg=7, mat="M_Wood")
    # stone sill
    if sill:
        nseg = max(2, int(L / 2.6))
        for side in (1, -1):
            for k in range(nseg):
                x0 = -L / 2 + L * k / nseg
                x1 = -L / 2 + L * (k + 1) / nseg
                y0, y1 = side * w(x0), side * w(x1)
                ang = math.atan2(y1 - y0, x1 - x0)
                mb.box(((x0 + x1) / 2, (y0 + y1) / 2, base_z + 0.05), (math.hypot(x1 - x0, y1 - y0) + 0.25, 0.5, 0.3),
                       "M_Stone", rot=(0, 0, ang))
        for sx in (-1, 1):
            mb.box((sx * L / 2, 0, base_z + 0.05), (0.5, 2 * w(sx * L / 2) + 0.3, 0.3), "M_Stone")
    # doors
    for wall, pos, dw, dh in doors:
        if wall in ("+y", "-y"):
            sd = 1 if wall == "+y" else -1
            y = sd * w(pos)
            ax, cen = (1, 0, 0), V(pos, y, 0)
            nrm = V(0, sd, 0)
        else:
            sd = 1 if wall == "+x" else -1
            cen = V(sd * L / 2, pos, 0)
            nrm = V(sd, 0, 0)
            ax = (0, 1, 0)
        a = V(ax)
        for s in (-1, 1):
            mb.box(cen + a * (s * (dw / 2 + 0.08)) + V(0, 0, base_z + dh / 2) + nrm * 0.04,
                   (0.16, 0.2, dh + 0.1) if wall in ("+y", "-y") else (0.2, 0.16, dh + 0.1), "M_Wood")
        lin = cen + V(0, 0, base_z + dh + 0.1) + nrm * 0.05
        mb.box(lin, (dw + 0.6, 0.22, 0.2) if wall in ("+y", "-y") else (0.22, dw + 0.6, 0.2), "M_Wood")
        leaf = cen + V(0, 0, base_z + dh / 2) - nrm * 0.06
        sz = (dw, 0.07, dh) if wall in ("+y", "-y") else (0.07, dw, dh)
        mb.box(leaf, sz, "M_Wood")
        for zz in (0.25, 0.75):
            mb.box(leaf + nrm * 0.04 + V(0, 0, (zz - 0.5) * dh), (dw * 0.9, 0.02, 0.07) if wall in ("+y", "-y") else (0.02, dw * 0.9, 0.07),
                   "M_Iron")
        # fill the wall above the door up to the roof
        topz = under_at_y(cen.x, cen.y if wall in ("+x", "-x") else w(cen.x)) if wall in ("+y", "-y") else None
        if wall in ("+x", "-x"):
            for k in range(4):
                y0 = pos - dw / 2 - 0.02 + (dw + 0.04) * k / 4
                y1 = pos - dw / 2 - 0.02 + (dw + 0.04) * (k + 1) / 4
                zb = base_z + dh + 0.2
                p = [V(cen.x, y0, zb), V(cen.x, y1, zb), V(cen.x, y1, under_at_y(cen.x, y1) + 0.02),
                     V(cen.x, y0, under_at_y(cen.x, y0) + 0.02)]
                if p[2].z > zb + 0.05:
                    mb.face([mb.v(q) for q in p], [(0, 0), (0.15, 0), (0.15, 1), (0, 1)], "M_Wood", False, nrm)
        elif topz is not None and topz > base_z + dh + 0.25:
            x0, x1 = pos - dw / 2 - 0.02, pos + dw / 2 + 0.02
            zb = base_z + dh + 0.2
            p = [V(x0, sd * w(x0), zb), V(x1, sd * w(x1), zb), V(x1, sd * w(x1), under_at_y(x1, w(x1)) + 0.02),
                 V(x0, sd * w(x0), under_at_y(x0, w(x0)) + 0.02)]
            mb.face([mb.v(q) for q in p], [(0, 0), (0.3, 0), (0.3, .3), (0, .3)], "M_Wood", False, nrm)
        mb.box(cen + nrm * 0.35 + V(0, 0, base_z - 0.08), (dw + 0.4, 0.7, 0.2) if wall in ("+y", "-y") else (0.7, dw + 0.4, 0.2),
               "M_Stone")
    # gable bargeboards with carved dragon finials
    if finials:
        for sx in (-1, 1):
            x = sx * (xe + 0.05)
            rp = top(sx * xe, 1.0, 1) + V(0, 0, 0.04)
            for side in (1, -1):
                ep = top(sx * xe, 0.0, side) + V(0, 0, 0.02)
                ep = V(x, ep.y, ep.z)
                rpp = V(x, 0, rp.z)
                d = (rpp - ep).normalized()
                end = rpp + d * 0.75
                scroll = [end + d * 0.18 + V(0, 0, 0.06), end + V(0, -side * 0.42, 0.34), end + V(0, -side * 0.62, 0.26),
                          end + V(0, -side * 0.66, 0.1)]
                path = [ep, ep.lerp(rpp, 0.5), rpp, end] + scroll
                sc = [(0.035, 0.16)] * 4 + [(0.035, 0.12), (0.035, 0.09), (0.035, 0.08), (0.035, 0.05)]
                mb.tube(path, RECT, sc, "M_Wood", side=(1, 0, 0), cap0=True, cap1=True)
                hd = end + V(0, -side * 0.62, 0.26)
                mb.sphere(hd + V(0, -side * 0.06, 0.05), 0.09, "M_Wood", seg=6, rings=4, scale=(0.5, 1.4, 0.8))
    # smoke hole: a raised wooden louvre on the ridge
    if smoke is not None:
        x = smoke
        zt = top(x, 1.0, 1).z
        for sy in (-1, 1):
            mb.box((x, sy * 0.42, zt + 0.05), (1.2, 0.1, 0.36), "M_Wood")
        for sx in (-1, 1):
            mb.box((x + sx * 0.55, 0, zt + 0.05), (0.1, 0.84, 0.36), "M_Wood")
        p = [V(x - 0.5, -0.37, zt + 0.1), V(x + 0.5, -0.37, zt + 0.1), V(x + 0.5, 0.37, zt + 0.1), V(x - 0.5, 0.37, zt + 0.1)]
        mb.face([mb.v(q) for q in p], [(0, 0), (0.5, 0), (0.5, 0.4), (0, 0.4)], "M_WoodTar", False, (0, 0, 1))
        for sx in (-1, 1):
            mb.box((x + sx * 0.5, 0, zt + 0.45), (0.08, 0.08, 0.6), "M_Wood")
        mb.box((x, 0, zt + 0.78), (1.4, 1.1, 0.06), "M_Wood", rot=(math.radians(8), 0, 0))
    # stilts (storehouse)
    if stilts:
        for sx in (-1, 0, 1):
            for sy in (-1, 1):
                x = sx * (L / 2 - 0.2)
                y = sy * (W / 2 - 0.2)
                mb.cyl((x, y, 0.25), (x, y, base_z - 0.1), 0.14, 0.12, seg=7, mat="M_Wood")
                mb.box((x, y, 0.12), (0.55, 0.55, 0.25), "M_Stone", rot=(0, 0, rng.uniform(0, 1)))
                mb.box((x, y, base_z - 0.16), (0.5, 0.5, 0.08), "M_Stone")
        mb.box((0, 0, base_z - 0.06), (L + 0.2, W + 0.2, 0.12), "M_Wood")
    return mb


def build_longhouse():
    return turf_house("SM_Longhouse", 25.0, 7.0, 2.0, 6.1, bow=0.16, sag=0.55, eave_over=0.55, gable_over=0.4, th=0.45,
                      buttress=1.9, doors=[("+y", 3.0, 1.1, 1.7), ("-x", 0.0, 1.2, 1.9)], smoke=-1.5)


def build_hut():
    return turf_house("SM_Hut", 7.0, 4.6, 1.8, 4.3, bow=0.05, sag=0.12, eave_over=0.45, gable_over=0.3, th=0.4,
                      doors=[("+x", 0.0, 1.0, 1.65)], smoke=-1.2)


def build_storehouse():
    return turf_house("SM_Storehouse", 3.6, 3.0, 1.7, 3.6, base_z=0.9, eave_over=0.4, gable_over=0.3, th=0.32,
                      doors=[("+x", 0.0, 0.85, 1.4)], sill=False, stilts=True, finials=True)


def build_smithy():
    mb = turf_house("SM_Smithy", 6.0, 4.2, 2.0, 4.0, eave_over=0.5, gable_over=0.3, th=0.38, open_front=True,
                    finials=False, doors=())
    # forge hearth (stone), anvil on a stump, quench tub, tool rack
    for k in range(10):
        a = 2 * PI * k / 10
        mb.box((-1.3 + 0.55 * math.cos(a), -0.5 + 0.4 * math.sin(a), 0.32), (0.42, 0.34, 0.64), "M_Stone",
               rot=(0, 0, a + rng.uniform(-0.3, 0.3)))
    mb.box((-1.3, -0.5, 0.5), (1.0, 0.7, 0.08), "M_WoodTar")       # charcoal bed
    mb.cyl((0.6, 0.3, 0), (0.6, 0.3, 0.55), 0.3, 0.28, seg=8, mat="M_Wood")
    mb.box((0.6, 0.3, 0.63), (0.42, 0.16, 0.16), "M_Iron")
    mb.box((0.6, 0.3, 0.73), (0.5, 0.18, 0.06), "M_Iron")
    mb.cone((0.85, 0.3, 0.73), (1.08, 0.3, 0.75), 0.06, seg=4, mat="M_Iron")
    barrel_into(mb, V(1.6, -0.9, 0), 0.6, 0.32)
    mb.box((0, -2.0, 1.3), (2.4, 0.08, 0.12), "M_Wood")
    for k in range(5):
        mb.box((-0.9 + 0.45 * k, -1.95, 1.0), (0.04, 0.03, 0.6), "M_Iron")
    return mb


# =========================================================================== SMALL PROPS
def barrel_into(mb, base, h=0.9, r=0.3, seg=16):
    rows = []
    nr = 8
    for i in range(nr + 1):
        z = h * i / nr
        rr = r * (0.86 + 0.14 * math.sin(PI * i / nr))
        rows.append([base + V(rr * math.cos(2 * PI * k / seg), rr * math.sin(2 * PI * k / seg), z) for k in range(seg)])
    mb.grid(rows, "M_Wood", closed_u=True, want=lambda i, j: rows[i][j] - (base + V(0, 0, h * i / nr)))
    for zc, end in ((0.03, -1), (h - 0.03, 1)):
        rr = r * 0.84
        ring = [base + V(rr * math.cos(2 * PI * k / seg), rr * math.sin(2 * PI * k / seg), zc) for k in range(seg)]
        mb.cap(ring if end > 0 else ring[::-1], "M_Wood", (0, 0, end))
    for f in (0.12, 0.38, 0.62, 0.88):
        z = h * f
        rr = r * (0.86 + 0.14 * math.sin(PI * f)) + 0.008
        rows = [[base + V((rr + dr) * math.cos(2 * PI * k / seg), (rr + dr) * math.sin(2 * PI * k / seg), z + dz) for k in range(seg)]
                for dz, dr in ((-0.03, 0), (-0.03, 0.006), (0.03, 0.006), (0.03, 0))]
        mb.grid(rows, "M_Iron", closed_u=True, want=lambda i, j, rows=rows, z=z: rows[i][j] - (base + V(0, 0, z)))


def build_barrel():
    mb = MB("SM_Barrel")
    barrel_into(mb, V(0, 0, 0))
    return mb


def build_crate():
    mb = MB("SM_Crate")
    L, W, H = 0.95, 0.7, 0.6
    for k in range(3):
        z = 0.04 + (H - 0.08) * (k + 0.5) / 3
        for sy in (-1, 1):
            mb.box((0, sy * (W / 2 - 0.01), z), (L - 0.04, 0.025, (H - 0.1) / 3 - 0.012), "M_Wood")
        for sx in (-1, 1):
            mb.box((sx * (L / 2 - 0.01), 0, z), (0.025, W - 0.04, (H - 0.1) / 3 - 0.012), "M_Wood")
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box((sx * (L / 2 - 0.03), sy * (W / 2 - 0.03), H / 2), (0.07, 0.07, H), "M_Wood")
    for k in range(4):
        mb.box((0, -W / 2 + W * (k + 0.5) / 4, H + 0.012), (L + 0.02, W / 4 - 0.012, 0.025), "M_Wood")
    mb.box((0, 0, 0.02), (L, W, 0.04), "M_Wood")
    for sx in (-1, 1):
        mb.box((sx * (L / 2 + 0.002), 0, H * 0.55), (0.012, W * 0.9, 0.05), "M_Iron")
    return mb


def build_woodpile():
    mb = MB("SM_WoodPile")
    rows_n, cols = 5, 9
    for r in range(rows_n):
        n = cols - (r % 2)
        for c in range(n):
            x = -1.0 + (c + 0.5 + 0.5 * (r % 2)) * 2.0 / cols
            z = 0.12 + r * 0.19
            rad = rng.uniform(0.085, 0.11)
            ln = rng.uniform(0.5, 0.62)
            yo = rng.uniform(-0.04, 0.04)
            sec = ellipse(6) if (r + c) % 3 else [(math.cos(a), math.sin(a)) for a in (0, 2.2, 4.1)] + [(0.0, 0.0)]
            if not (r + c) % 3:
                sec = [(-1, -0.8), (1, -0.8), (0.0, 1.0)]
            mb.tube([V(x, -ln / 2 + yo, z), V(x, ln / 2 + yo, z)], sec, rad, "M_Wood", side=(rng.uniform(-1, 1), 0, 1),
                    cap0=True, cap1=True)
    for sx in (-1, 1):
        mb.cyl((sx * 1.08, 0, 0), (sx * 1.08, 0, 1.15), 0.06, seg=6, mat="M_Wood")
    for sy in (-1, 1):
        mb.box((0, sy * 0.18, 0.03), (2.2, 0.12, 0.06), "M_Wood")
    return mb


PIER_LEN = 5.0


def build_pier(end=False):
    mb = MB("SM_PierEnd" if end else "SM_PierSection")
    deck = 1.0
    n = 19
    for k in range(n):
        x = -PIER_LEN / 2 + PIER_LEN * (k + 0.5) / n
        mb.box((x + rng.uniform(-0.01, 0.01), rng.uniform(-0.05, 0.05), deck - 0.03 + rng.uniform(-0.01, 0.01)),
               (PIER_LEN / n - 0.025, 2.6 + rng.uniform(-0.1, 0.1), 0.06), "M_Wood", rot=(0, 0, rng.uniform(-0.02, 0.02)))
    for sy in (-1, 1):
        mb.box((0, sy * 1.0, deck - 0.19), (PIER_LEN, 0.2, 0.26), "M_Wood")
    for sx in (-1, 1):
        x = sx * 1.9
        mb.box((x, 0, deck - 0.4), (0.22, 2.7, 0.22), "M_Wood")
        for sy in (-1, 1):
            topz = deck + (1.0 if end and sx > 0 else -0.06)
            mb.cyl((x, sy * 1.2, -3.0), (x, sy * 1.2, topz), 0.16, 0.15, seg=8, mat="M_Wood", rings=3)
    for sy in (-1, 1):
        mb.box((0, sy * 1.22, -0.6), (3.9, 0.1, 0.16), "M_Wood", rot=(0, math.atan2(1.2, 3.8), 0))
    if end:
        # ladder down to the water on the end face
        for sy in (-0.3, 0.3):
            mb.box((PIER_LEN / 2 + 0.05, sy, 0.2), (0.07, 0.07, 1.8), "M_Wood")
        for k in range(5):
            mb.box((PIER_LEN / 2 + 0.05, 0, -0.5 + 0.32 * k), (0.06, 0.6, 0.05), "M_Wood")
    return mb


PAL_LEN = 6.0


def _pal_log(mb, x, y=0.0):
    r = rng.uniform(0.13, 0.16)
    h = rng.uniform(3.1, 3.55)
    lean = V(rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0)
    base = V(x, y, -0.4)
    tp = V(x, y, h) + lean
    mb.tube([base, base.lerp(tp, 0.5), tp], ellipse(7), [r, r * 0.97, r * 0.92], "M_Wood", side=(1, 0, 0))
    mb.cone(tp, tp + V(0, 0, 0.42) + lean * 0.3, r * 0.92, seg=7, mat="M_Wood", cap=False)


def _pal_bank(mb, x0, x1):
    sec = [(-1.4, -0.05), (-0.8, 0.25), (0, 0.42), (0.8, 0.25), (1.4, -0.05)]
    rows = [[V(x, sy, z) for sy, z in sec] for x in (x0, (x0 + x1) / 2, x1)]
    mb.grid(rows, "M_Turf", want=(0, 0, 1))


def build_palisade():
    mb = MB("SM_PalisadeWall")
    n = 20
    for k in range(n):
        _pal_log(mb, -PAL_LEN / 2 + PAL_LEN * (k + 0.5) / n)
    for z in (1.0, 2.3):
        mb.box((0, -0.24, z), (PAL_LEN, 0.12, 0.18), "M_Wood")
    _pal_bank(mb, -PAL_LEN / 2, PAL_LEN / 2)
    return mb


def build_gate():
    mb = MB("SM_PalisadeGate")
    n = 20
    for k in range(n):
        x = -PAL_LEN / 2 + PAL_LEN * (k + 0.5) / n
        if abs(x) < 1.85:
            continue
        _pal_log(mb, x)
    for sx in (-1, 1):
        mb.cyl((sx * 1.7, 0, -0.5), (sx * 1.7, 0, 4.7), 0.23, 0.21, seg=10, mat="M_Wood", rings=3)
        mb.cone((sx * 1.7, 0, 4.7), (sx * 1.7, 0, 5.05), 0.21, seg=10, mat="M_Wood", cap=False)
        mb.box((sx * 2.4, -0.24, 1.0), (1.2, 0.12, 0.18), "M_Wood")
        mb.box((sx * 2.4, -0.24, 2.3), (1.2, 0.12, 0.18), "M_Wood")
    mb.box((0, 0, 4.05), (4.2, 0.34, 0.3), "M_Wood")
    for sy in (-1, 1):
        mb.box((0, sy * 0.42, 4.55), (4.4, 0.9, 0.06), "M_Wood", rot=(sy * math.radians(28), 0, 0))
    # double doors: left closed, right ajar
    for sx, ang in ((-1, 0.0), (1, math.radians(-28))):
        hinge = V(sx * 1.47, 0, 0)
        R = Matrix.Rotation(ang * sx, 3, "Z")
        for k in range(6):
            lx = -sx * (0.125 + 0.25 * k)
            c = hinge + R @ V(lx, 0, 1.85)
            mb.box(c, (0.24, 0.09, 3.7 + 0.05 * (k % 2)), "M_Wood", rot=R)
        for z in (0.7, 1.9, 3.1):
            c = hinge + R @ V(-sx * 0.74, -0.06, z)
            mb.box(c, (1.42, 0.025, 0.09), "M_Iron", rot=R)
        mb.box(hinge + R @ V(-sx * 0.74, -0.1, 2.4), (1.5, 0.1, 0.14), "M_Wood", rot=R)
    _pal_bank(mb, -PAL_LEN / 2, -1.95)
    _pal_bank(mb, 1.95, PAL_LEN / 2)
    return mb


def build_watchtower():
    mb = MB("SM_Watchtower")
    plat = 7.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.cyl((sx * 1.5, sy * 1.5, -0.4), (sx * 1.25, sy * 1.25, 9.4), 0.15, 0.12, seg=8, mat="M_Wood", rings=3)
    # bracing
    for a, b in (((1, 1), (1, -1)), ((1, -1), (-1, -1)), ((-1, -1), (-1, 1)), ((-1, 1), (1, 1))):
        for z0, z1 in ((0.6, 3.6), (3.8, 6.8)):
            fa = 1.5 - 0.25 * z0 / 9.8
            fb = 1.5 - 0.25 * z1 / 9.8
            p0 = V(a[0] * fa, a[1] * fa, z0)
            p1 = V(b[0] * fb, b[1] * fb, z1)
            q0 = V(b[0] * fa, b[1] * fa, z0)
            q1 = V(a[0] * fb, a[1] * fb, z1)
            for u, v in ((p0, p1), (q0, q1)):
                mb.cyl(u, v, 0.06, seg=5, mat="M_Wood", cap0=False, cap1=False)
            mb.cyl(p0, q0, 0.07, seg=5, mat="M_Wood", cap0=False, cap1=False)
    # platform
    for k in range(11):
        y = -1.6 + 3.2 * (k + 0.5) / 11
        mb.box((0, y, plat), (3.4, 3.2 / 11 - 0.02, 0.07), "M_Wood")
    for sx in (-1, 1):
        mb.box((sx * 1.35, 0, plat - 0.15), (0.16, 3.4, 0.2), "M_Wood")
    # breastwork boards
    for side in range(4):
        R = Matrix.Rotation(side * PI / 2, 3, "Z")
        for k in range(11):
            u = -1.65 + 3.3 * (k + 0.5) / 11
            c = R @ V(1.72, u, plat + 0.6)
            mb.box(c, (0.04, 3.3 / 11 - 0.01, 1.15 + 0.06 * (k % 2)), "M_Wood", rot=R)
        mb.box(R @ V(1.74, 0, plat + 1.2), (0.12, 3.6, 0.1), "M_Wood", rot=R)
    # roof (wooden pyramid)
    apex = V(0, 0, 11.0)
    eaves = [V(sx * 2.0, sy * 2.0, 9.3) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    for k in range(4):
        a, b = eaves[k], eaves[(k + 1) % 4]
        ids = [mb.v(a), mb.v(b), mb.v(apex)]
        mb.face(ids, [(0, 0), (2, 0), (1, 1)], "M_WoodTar", False, ((a + b) / 2 - V(0, 0, 9.3)) + V(0, 0, 1.5))
        ids = [mb.v(a + V(0, 0, -0.06)), mb.v(b + V(0, 0, -0.06)), mb.v(apex + V(0, 0, -0.06))]
        mb.face(ids, [(0, 0), (2, 0), (1, 1)], "M_Wood", False, V(0, 0, -1))
        mb.cyl(a, apex, 0.06, seg=5, mat="M_Wood", cap0=True, cap1=False)
    # ladder on +X face
    for sy in (-0.3, 0.3):
        mb.box((2.3, sy, plat / 2), (0.08, 0.08, plat + 0.6), "M_Wood", rot=(0, -math.atan2(0.9, plat), 0))
    for k in range(20):
        z = 0.3 + (plat - 0.3) * k / 19
        mb.box((2.3 + (plat / 2 - z) * 0.9 / plat, 0, z), (0.05, 0.6, 0.05), "M_Wood")
    return mb


def build_banner_pole():
    mb = MB("SM_BannerPole")
    mb.cyl((0, 0, -0.3), (0, 0, 5.1), 0.06, 0.045, seg=8, mat="M_Wood", rings=3)
    mb.cone((0, 0, 5.1), (0, 0, 5.5), 0.05, seg=6, mat="M_Iron", cap=False)
    mb.cyl((0, -0.72, 4.85), (0, 0.72, 4.85), 0.03, seg=6, mat="M_Wood")
    for k in range(6):
        a = 2 * PI * k / 6
        mb.box((0.28 * math.cos(a), 0.28 * math.sin(a), 0.1), (0.3, 0.26, 0.22), "M_Stone", rot=(0, 0, a))
    return mb


BANNER_ATTACH = V(0.04, 0.0, 4.82)


def build_banner_cloth():
    mb = MB("SM_BannerCloth")
    nu, nv = 9, 13
    Wd, Ht = 1.3, 2.0
    rows = []
    for i in range(nv):
        v = i / (nv - 1)   # 0 bottom (tails) .. 1 top (crossbar)
        row = []
        for j in range(nu):
            u = j / (nu - 1)
            tail = -0.32 if (i == 0 and j in (1, 4, 7)) else 0.0
            y = (u - 0.5) * Wd
            z = -(1 - v) * Ht + tail * (1 - v)
            x = 0.12 * math.sin(PI * 1.3 * u + 2.0 * (1 - v)) * (1 - v) + 0.03 * math.sin(4 * PI * u)
            row.append(V(x, y, z))
        rows.append(row)
    mb.grid(rows, "M_Banner", uv=lambda i, j: (j / (nu - 1), i / (nv - 1)), want=(1, 0, 0))
    return mb
