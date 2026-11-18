"""Mesh-building helpers for the Viking prop kit (1 Blender unit = 1 m, Z up, +X forward).

MB accumulates vertices / faces with explicit per-corner UVs and material slots, then
emits a triangulated bpy mesh object. UV convention: wood grain runs along V, so every
helper puts V along the length of a plank, post or log. Each primitive gets a random UV
offset so tiled textures never repeat identically between pieces.
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

# metres covered by one UV unit, per kit material (must match texture authoring)
TEX_M = {"M_Wood": 2.0, "M_WoodTar": 2.0, "M_Turf": 4.0, "M_Iron": 1.0, "M_Stone": 2.0,
         "M_Shields": 1.0, "M_Sail": 1.0, "M_Banner": 1.0}

rng = random.Random(4242)


def V(*a):
    if len(a) == 1:
        return Vector(a[0])
    return Vector(a)


def ruv():
    return (rng.random(), rng.random())


class MB:
    def __init__(self, name):
        self.name = name
        self.V = []
        self.F = []
        self.UV = []
        self.M = []
        self.S = []
        self.mats = []

    # ------------------------------------------------------------------ core
    def mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def v(self, p):
        self.V.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.V) - 1

    def face(self, idx, uvs, mat, smooth=True, want=None):
        """Add a face. If `want` (a direction) is given, flip winding to face it."""
        idx = list(idx)
        uvs = list(uvs)
        if want is not None and len(idx) >= 3:
            p = [Vector(self.V[i]) for i in idx]
            nrm = Vector((0, 0, 0))
            for k in range(len(p)):
                a, b = p[k], p[(k + 1) % len(p)]
                nrm += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
            if nrm.dot(Vector(want)) < 0:
                idx.reverse()
                uvs.reverse()
        self.F.append(idx)
        self.UV.append(uvs)
        self.M.append(self.mi(mat))
        self.S.append(smooth)

    def tri_count(self):
        return sum(len(f) - 2 for f in self.F)

    # ------------------------------------------------------------------ primitives
    def grid(self, rows, mat, closed_u=False, smooth=True, uv=None, want=None, uv_scale=None, off=None):
        """rows: list (along V) of lists (along U) of points. uv(i, j) -> (u, v) optional."""
        m = TEX_M.get(mat, 1.0) if uv_scale is None else uv_scale
        o = ruv() if off is None else off
        nr, nc = len(rows), len(rows[0])
        ids = [[self.v(p) for p in row] for row in rows]
        if uv is None:
            # cumulative arc-length UVs
            us = []
            for row in rows:
                acc = [0.0]
                pts = list(row) + ([row[0]] if closed_u else [])
                for k in range(1, len(pts)):
                    acc.append(acc[-1] + (Vector(pts[k]) - Vector(pts[k - 1])).length)
                us.append(acc)
            cen = [sum((Vector(p) for p in row), Vector()) / len(row) for row in rows]
            vs = [0.0]
            for k in range(1, nr):
                vs.append(vs[-1] + (cen[k] - cen[k - 1]).length)

            def uv(i, j):
                return (us[i][j] / m + o[0], vs[i] / m + o[1])
        ncu = nc if closed_u else nc - 1
        for i in range(nr - 1):
            for j in range(ncu):
                j1 = (j + 1) % nc
                ju = j + 1  # uv index (no wrap so seam gets full length)
                quad = [ids[i][j], ids[i][j1], ids[i + 1][j1], ids[i + 1][j]]
                uvq = [uv(i, j), uv(i, ju), uv(i + 1, ju), uv(i + 1, j)]
                w = None
                if want is not None:
                    w = want(i, j) if callable(want) else want
                self.face(quad, uvq, mat, smooth, w)
        return ids

    def cap(self, pts, mat, want, center=None, uv_scale=None):
        """Planar n-gon cap with planar UVs."""
        m = TEX_M.get(mat, 1.0) if uv_scale is None else uv_scale
        pts = [Vector(p) for p in pts]
        n = Vector(want).normalized()
        a = (pts[1] - pts[0])
        if a.length < 1e-8:
            a = n.orthogonal()
        a = (a - n * a.dot(n)).normalized()
        b = n.cross(a)
        o = ruv()
        ids = [self.v(p) for p in pts]
        uvs = [((p - pts[0]).dot(a) / m + o[0], (p - pts[0]).dot(b) / m + o[1]) for p in pts]
        self.face(ids, uvs, mat, False, n)

    def tube(self, path, section, scales, mat, side=(0, 1, 0), cap0=False, cap1=False, smooth=True,
             uv_scale=None, transport=False):
        """Sweep a closed 2D section (list of (s, u) points, counter-clockwise) along a path.
        scales: float, (sx, su) or a list of either per path point."""
        path = [Vector(p) for p in path]
        n = len(path)
        if not isinstance(scales, list):
            scales = [scales] * n
        rings = []
        prev_s = None
        for i, p in enumerate(path):
            if i == 0:
                t = path[1] - path[0]
            elif i == n - 1:
                t = path[-1] - path[-2]
            else:
                t = (path[i + 1] - path[i - 1])
            t.normalize()
            if transport and prev_s is not None:
                s = prev_s - t * prev_s.dot(t)
            else:
                s = Vector(side) - t * Vector(side).dot(t)
                if s.length < 1e-4:
                    s = t.orthogonal()
            s.normalize()
            prev_s = s
            u = t.cross(s)
            sc = scales[i]
            sx, su = (sc, sc) if isinstance(sc, (int, float)) else sc
            rings.append([p + s * (q[0] * sx) + u * (q[1] * su) for q in section])
        cen = path

        def want(i, j):
            q = rings[i][j]
            return q - cen[i]
        ids = self.grid(rings, mat, closed_u=True, smooth=smooth, want=want, uv_scale=uv_scale)
        if cap0:
            self.cap(rings[0], mat, -(path[1] - path[0]), uv_scale=uv_scale)
        if cap1:
            self.cap(rings[-1], mat, (path[-1] - path[-2]), uv_scale=uv_scale)
        return rings

    def box(self, center, size, mat, rot=None, uv_scale=None, smooth=False):
        """Oriented box. rot: 3x3 Matrix or Euler-like (rx, ry, rz) in radians."""
        m = TEX_M.get(mat, 1.0) if uv_scale is None else uv_scale
        c = Vector(center)
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        R = Matrix.Identity(3)
        if rot is not None:
            if isinstance(rot, Matrix):
                R = rot.to_3x3()
            else:
                from mathutils import Euler
                R = Euler(rot, "XYZ").to_matrix()
        long_ax = max(range(3), key=lambda k: size[k])
        o = ruv()
        corners = {}
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    corners[(sx, sy, sz)] = c + R @ Vector((sx * hx, sy * hy, sz * hz))
        faces = [
            (0, 1, [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
            (0, -1, [(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)]),
            (1, 1, [(1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)]),
            (1, -1, [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),
            (2, 1, [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
            (2, -1, [(-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)]),
        ]
        half = (hx, hy, hz)
        for ax, sg, cs in faces:
            others = [k for k in range(3) if k != ax]
            # V along the longest in-plane axis (grain along length)
            if long_ax in others:
                va = long_ax
                ua = [k for k in others if k != long_ax][0]
            else:
                ua, va = others
            ids = [self.v(corners[q]) for q in cs]
            uvs = [((q[ua] * half[ua]) / m + o[0], (q[va] * half[va]) / m + o[1]) for q in cs]
            nrm = R @ Vector([sg if k == ax else 0 for k in range(3)])
            self.face(ids, uvs, mat, smooth, nrm)

    def cyl(self, p0, p1, r0, r1=None, seg=8, mat="M_Wood", cap0=True, cap1=True, side=(0, 0, 1), rings=2):
        r1 = r0 if r1 is None else r1
        p0, p1 = Vector(p0), Vector(p1)
        sec = [(math.cos(2 * math.pi * k / seg), math.sin(2 * math.pi * k / seg)) for k in range(seg)]
        path = [p0.lerp(p1, i / (rings - 1)) for i in range(rings)]
        sc = [r0 + (r1 - r0) * i / (rings - 1) for i in range(rings)]
        d = (p1 - p0).normalized()
        sd = Vector(side)
        if abs(d.dot(sd)) > 0.95:
            sd = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
        return self.tube(path, sec, sc, mat, side=sd, cap0=cap0, cap1=cap1)

    def cone(self, base, tip, r, seg=6, mat="M_Wood", side=(0, 0, 1), cap=True):
        base, tip = Vector(base), Vector(tip)
        d = (tip - base).normalized()
        sd = Vector(side)
        if abs(d.dot(sd)) > 0.95:
            sd = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
        s = (sd - d * sd.dot(d)).normalized()
        u = d.cross(s)
        ring = [base + s * (r * math.cos(2 * math.pi * k / seg)) + u * (r * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
        m = TEX_M.get(mat, 1.0)
        o = ruv()
        ti = self.v(tip)
        ids = [self.v(p) for p in ring]
        L = (tip - base).length
        for k in range(seg):
            a, b = ids[k], ids[(k + 1) % seg]
            self.face([a, b, ti], [(k * r / m + o[0], o[1]), ((k + 1) * r / m + o[0], o[1]), ((k + .5) * r / m + o[0], L / m + o[1])],
                      mat, True, ((ring[k] + ring[(k + 1) % seg]) / 2 - base))
        if cap:
            self.cap(ring, mat, -d)

    def sphere(self, c, r, mat, seg=8, rings=5, scale=(1, 1, 1)):
        c = Vector(c)
        rows = []
        for i in range(rings + 1):
            th = math.pi * (i / rings) - math.pi / 2
            rows.append([c + Vector((r * scale[0] * math.cos(th) * math.cos(2 * math.pi * k / seg),
                                     r * scale[1] * math.cos(th) * math.sin(2 * math.pi * k / seg),
                                     r * scale[2] * math.sin(th))) for k in range(seg)])
        self.grid(rows, mat, closed_u=True, want=lambda i, j: Vector(rows[i][j]) - c)

    # ------------------------------------------------------------------ output
    def build(self, materials, sharp_deg=40.0, location=(0, 0, 0), name=None):
        name = name or self.name
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.V, [], self.F)
        uvl = me.uv_layers.new(name="UVMap")
        flat = [c for f in self.UV for uv in f for c in uv]
        uvl.data.foreach_set("uv", flat)
        me.polygons.foreach_set("material_index", self.M)
        me.polygons.foreach_set("use_smooth", self.S)
        for mname in self.mats:
            me.materials.append(materials[mname])
        me.validate(clean_customdata=False)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
        bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(me)
        bm.free()
        me.set_sharp_from_angle(angle=math.radians(sharp_deg))
        ob = bpy.data.objects.new(name, me)
        ob.location = location
        bpy.context.scene.collection.objects.link(ob)
        return ob


def tri_count(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)
