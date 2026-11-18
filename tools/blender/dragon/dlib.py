"""Shared helpers for the procedural dragon + rider build (Blender 5.0, headless).

Geometry is generated parametrically (lofted tubes / sheets) so every vertex knows its
bone weights at creation time; materials are procedural Cycles node trees that get baked
to PNG texture sets for Unreal / three.js. Imported by build_dragon.py / build_rider.py.
"""
import math
import os
import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix, Quaternion

OUT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                        "Game", "DragonRider", "Saved", "Generated", "Dragon"))
os.makedirs(OUT_DIR, exist_ok=True)
TEX_DIR = os.path.join(OUT_DIR, "Textures")
os.makedirs(TEX_DIR, exist_ok=True)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def sstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------- curves
def catmull(ctrl, n, dims=3):
    """Catmull-Rom through control rows (K, D); first `dims` columns are positions.
    Returns (samples (n, D) uniform in arc length, arc lengths (n,))."""
    P = np.asarray(ctrl, float)
    K = len(P)
    if K == 2:
        P = np.vstack([P[0], (P[0] + P[1]) / 2, P[1]])
        K = 3
    E = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    dense = []
    for i in range(K - 1):
        p0, p1, p2, p3 = E[i], E[i + 1], E[i + 2], E[i + 3]
        for t in np.linspace(0, 1, 48, endpoint=False):
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(P[-1])
    dense = np.array(dense)
    seg = np.linalg.norm(np.diff(dense[:, :dims], axis=0), axis=1)
    L = np.concatenate([[0], np.cumsum(seg)])
    tg = np.linspace(0, L[-1], n)
    out = np.stack([np.interp(tg, L, dense[:, k]) for k in range(dense.shape[1])], 1)
    return out, tg


def frames(C, up0):
    """Parallel-transport-ish frames along polyline C (n,3). Returns T, U(up), S(side=U x T... left)."""
    n = len(C)
    T = np.gradient(C, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-12
    U = np.zeros_like(C)
    u = np.asarray(up0, float)
    for i in range(n):
        u = u - np.dot(u, T[i]) * T[i]
        nu = np.linalg.norm(u)
        if nu < 1e-6:
            u = np.cross(T[i], [0.0, 1.0, 0.0]) if abs(T[i][1]) < 0.9 else np.cross(T[i], [1.0, 0, 0])
            nu = np.linalg.norm(u)
        u = u / nu
        U[i] = u
    S = np.cross(U, T)
    return T, U, S


# ----------------------------------------------------------------------------- mesh accumulator
class Acc:
    """Collects verts / faces / per-vertex weights / attributes / face materials.
    attrs: name -> scalar | 3-tuple | per-vertex array (c,) or (c,3). Vector attrs listed in vec."""

    def __init__(self, vec=('eyedir',)):
        self.V, self.F, self.M, self.W = [], [], [], []
        self.A = {}
        self.vec = set(vec)
        self.n = 0

    def _default(self, k):
        return (0.0, 0.0, 0.0) if k in self.vec else 0.0

    def add(self, verts, faces, mat=0, weights=None, attrs=None):
        verts = np.asarray(verts, float).reshape(-1, 3)
        base = self.n
        c = len(verts)
        self.V.extend(verts.tolist())
        if weights is None:
            weights = [{}] * c
        elif isinstance(weights, dict):
            weights = [weights] * c
        assert len(weights) == c, (len(weights), c)
        self.W.extend(weights)
        attrs = attrs or {}
        for k in attrs:
            if k not in self.A:
                self.A[k] = [self._default(k)] * self.n
        for k in self.A:
            if k not in attrs:
                self.A[k].extend([self._default(k)] * c)
                continue
            v = attrs[k]
            if k in self.vec:
                arr = np.asarray(v, float)
                if arr.ndim == 1:
                    self.A[k].extend([tuple(arr)] * c)
                else:
                    self.A[k].extend([tuple(r) for r in arr.reshape(c, 3)])
            else:
                if np.isscalar(v):
                    self.A[k].extend([float(v)] * c)
                else:
                    self.A[k].extend([float(x) for x in np.asarray(v, float).reshape(c)])
        self.n += c
        for f in faces:
            self.F.append([base + i for i in f])
            self.M.append(mat)
        return base

    def rings(self, R, closed=True, cap0=False, cap1=False, mat=0, weights=None, attrs=None):
        """R: (nr, ns, 3). weights: dict | list per ring | list per vertex.
        attrs values: scalar | per-ring (nr,) | per-vertex (nr*ns,) / (nr*ns,3)."""
        R = np.asarray(R, float)
        nr, ns, _ = R.shape
        faces = []
        jm = ns if closed else ns - 1
        for i in range(nr - 1):
            for j in range(jm):
                j2 = (j + 1) % ns
                faces.append([i * ns + j, i * ns + j2, (i + 1) * ns + j2, (i + 1) * ns + j])
        if weights is None or isinstance(weights, dict):
            wl = [weights or {}] * (nr * ns)
        elif len(weights) == nr * ns:
            wl = list(weights)
        else:
            wl = [weights[i] for i in range(nr) for _ in range(ns)]
        al = {}
        for k, v in (attrs or {}).items():
            if k in self.vec:
                arr = np.asarray(v, float)
                al[k] = np.tile(arr, (nr * ns, 1)) if arr.ndim == 1 else arr.reshape(nr * ns, 3)
            elif np.isscalar(v):
                al[k] = np.full(nr * ns, float(v))
            else:
                arr = np.asarray(v, float).ravel()
                al[k] = np.repeat(arr, ns) if arr.size == nr else arr
        base = self.add(R.reshape(-1, 3), faces, mat, wl, al)
        for cap, ring in ((cap0, 0), (cap1, nr - 1)):
            if not (closed and cap):
                continue
            c = R[ring].mean(0)
            vi = ring * ns
            ci = self.add([c], [], mat, [wl[vi]], {k: (a[vi]) for k, a in al.items()})
            rb = base + ring * ns
            for j in range(ns):
                if ring == 0:
                    self.F.append([ci, rb + (j + 1) % ns, rb + j])
                else:
                    self.F.append([ci, rb + j, rb + (j + 1) % ns])
                self.M.append(mat)
        return base

    def grid(self, P, mat=0, weights=None, attrs=None):
        """Open sheet P: (nu, nv, 3)."""
        return self.rings(P, closed=False, mat=mat, weights=weights, attrs=attrs)

    def build(self, name, materials):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.V, [], self.F)
        me.update()
        for m in materials:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", self.M)
        me.polygons.foreach_set("use_smooth", [True] * len(self.F))
        for k, vals in self.A.items():
            if k in self.vec:
                at = me.attributes.new(k, 'FLOAT_VECTOR', 'POINT')
                at.data.foreach_set("vector", np.array(vals, float).ravel())
            else:
                at = me.attributes.new(k, 'FLOAT', 'POINT')
                at.data.foreach_set("value", np.array(vals, float))
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        groups = {}
        for vi, wd in enumerate(self.W):
            for b, w in wd.items():
                if w > 1e-4:
                    groups.setdefault(b, {}).setdefault(round(w, 4), []).append(vi)
        for b, byw in groups.items():
            vg = ob.vertex_groups.new(name=b)
            for w, idx in byw.items():
                vg.add(idx, w, 'REPLACE')
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        return ob


def loft(acc, rows, n_rings, n_seg, up=(0, 0, 1), cap0=True, cap1=True, mat=0,
         weight_fn=None, attrs=None, section=None, closed=True):
    """Loft a tube along a Catmull-Rom curve through rows (x, y, z, r_side, r_up).
    section(t, theta, L) -> radial multiplier; weight_fn(t, L) -> dict;
    attrs: name -> fn(t, L) -> scalar. Returns dict(C, L, ctrlL, T, U, S)."""
    rows = np.asarray(rows, float)
    Sm, L = catmull(rows, n_rings)
    C = Sm[:, :3]
    T, U, S = frames(C, up)
    th = np.linspace(0, 2 * math.pi, n_seg, endpoint=False)
    R = np.zeros((n_rings, n_seg, 3))
    t_all = L / L[-1]
    for i in range(n_rings):
        ra, rb = max(Sm[i, 3], 0.0), max(Sm[i, 4], 0.0)
        m = np.ones(n_seg) if section is None else np.array([section(t_all[i], a, L[i]) for a in th])
        R[i] = C[i] + np.outer(np.sin(th) * ra * m, S[i]) + np.outer(np.cos(th) * rb * m, U[i])
    weights = [weight_fn(t_all[i], L[i]) for i in range(n_rings)] if weight_fn else None
    at = {k: np.array([f(t_all[i], L[i]) for i in range(n_rings)]) for k, f in (attrs or {}).items()}
    acc.rings(R, closed=closed, cap0=cap0, cap1=cap1, mat=mat, weights=weights, attrs=at)
    ctrlL = [float(L[np.argmin(np.linalg.norm(C - r[:3], axis=1))]) for r in rows]
    ctrlL[0], ctrlL[-1] = 0.0, float(L[-1])
    return dict(C=C, L=L, ctrlL=ctrlL, T=T, U=U, S=S)


# ----------------------------------------------------------------------------- weights
def chain_weights(L, joints, names, blend=0.35, blend_override=None):
    """joints: arc positions (len n+1) of a bone chain names (len n). Joint-blended weights."""
    n = len(names)
    if L <= joints[0]:
        return {names[0]: 1.0}
    if L >= joints[-1]:
        return {names[-1]: 1.0}
    k = int(np.searchsorted(joints, L) - 1)
    k = max(0, min(n - 1, k))
    a, b = joints[k], joints[k + 1]
    w = {names[k]: 1.0}

    def rad(j):
        if blend_override and j in blend_override:
            return blend_override[j]
        la = joints[j] - joints[j - 1] if j - 1 >= 0 else 1e9
        lb = joints[j + 1] - joints[j] if j + 1 < len(joints) else 1e9
        return blend * min(la, lb)

    if k > 0:
        r = rad(k)
        d = L - a
        if d < r:
            t = 0.5 + 0.5 * d / r
            t = t * t * (3 - 2 * t) if False else t
            return {names[k]: t, names[k - 1]: 1 - t}
    if k < n - 1:
        r = rad(k + 1)
        d = b - L
        if d < r:
            t = 0.5 + 0.5 * d / r
            return {names[k]: t, names[k + 1]: 1 - t}
    return w


def wmix(*pairs):
    out = {}
    for f, d in pairs:
        if f <= 0:
            continue
        for k, v in d.items():
            out[k] = out.get(k, 0.0) + f * v
    s = sum(out.values())
    if s > 0:
        out = {k: v / s for k, v in out.items()}
    # keep top 4
    if len(out) > 4:
        top = sorted(out.items(), key=lambda kv: -kv[1])[:4]
        s = sum(v for _, v in top)
        out = {k: v / s for k, v in top}
    return out


# ----------------------------------------------------------------------------- node helper
class NB:
    def __init__(self, mat):
        self.mat = mat
        self.nt = mat.node_tree
        self.N = self.nt.nodes
        self.Lk = self.nt.links

    def new(self, t, **props):
        n = self.N.new(t)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def _in(self, sock, v):
        if v is None:
            return
        if isinstance(v, bpy.types.NodeSocket):
            self.Lk.new(v, sock)
        else:
            if isinstance(v, (tuple, list)) and len(v) == 3 and sock.type == 'RGBA':
                v = (v[0], v[1], v[2], 1.0)
            sock.default_value = v

    def math(self, op, a, b=None, clamp=False):
        n = self.new("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        return n.outputs[0]

    def mix(self, fac, a, b, blend='MIX'):
        n = self.new("ShaderNodeMix", data_type='RGBA', blend_type=blend)
        self._in(n.inputs[0], fac)
        self._in(n.inputs[6], a)
        self._in(n.inputs[7], b)
        return n.outputs[2]

    def mixf(self, fac, a, b):
        n = self.new("ShaderNodeMix", data_type='FLOAT')
        self._in(n.inputs[0], fac)
        self._in(n.inputs[2], a)
        self._in(n.inputs[3], b)
        return n.outputs[0]

    def maprange(self, v, a, b, c=0.0, d=1.0, interp='LINEAR'):
        n = self.new("ShaderNodeMapRange", interpolation_type=interp, clamp=True)
        self._in(n.inputs[0], v)
        n.inputs[1].default_value = a
        n.inputs[2].default_value = b
        n.inputs[3].default_value = c
        n.inputs[4].default_value = d
        return n.outputs[0]

    def attr(self, name):
        n = self.new("ShaderNodeAttribute", attribute_type='GEOMETRY', attribute_name=name)
        return n

    def coord(self):
        return self.new("ShaderNodeTexCoord")

    def vscale(self, vec, s):
        n = self.new("ShaderNodeVectorMath", operation='MULTIPLY')
        self._in(n.inputs[0], vec)
        self._in(n.inputs[1], s if not np.isscalar(s) else (s, s, s))
        return n.outputs[0]

    def vadd(self, a, b):
        n = self.new("ShaderNodeVectorMath", operation='ADD')
        self._in(n.inputs[0], a)
        self._in(n.inputs[1], b)
        return n.outputs[0]

    def voronoi(self, vec, scale, feature='F1', rand=1.0, dim='3D'):
        n = self.new("ShaderNodeTexVoronoi", feature=feature, voronoi_dimensions=dim)
        self._in(n.inputs['Vector'], vec)
        n.inputs['Scale'].default_value = scale
        n.inputs['Randomness'].default_value = rand
        return n

    def noise(self, vec, scale, detail=4.0, rough=0.5, distort=0.0):
        n = self.new("ShaderNodeTexNoise")
        self._in(n.inputs['Vector'], vec)
        n.inputs['Scale'].default_value = scale
        n.inputs['Detail'].default_value = detail
        n.inputs['Roughness'].default_value = rough
        n.inputs['Distortion'].default_value = distort
        return n

    def ramp(self, fac, stops):
        n = self.new("ShaderNodeValToRGB")
        self._in(n.inputs[0], fac)
        el = n.color_ramp.elements
        while len(el) > 2:
            el.remove(el[-1])
        for i, (p, c) in enumerate(stops):
            e = el[i] if i < 2 else el.new(p)
            e.position = p
            e.color = (c[0], c[1], c[2], 1.0)
        return n.outputs[0]

    def sep(self, vec):
        n = self.new("ShaderNodeSeparateXYZ")
        self._in(n.inputs[0], vec)
        return n.outputs

    def bump(self, height, strength=1.0, distance=0.01, normal=None):
        n = self.new("ShaderNodeBump")
        self._in(n.inputs['Height'], height)
        n.inputs['Strength'].default_value = strength
        n.inputs['Distance'].default_value = distance
        if normal is not None:
            self._in(n.inputs['Normal'], normal)
        return n.outputs[0]


def pbr_material(name, build):
    """build(nb) -> dict(color=, rough=, metal=, normal=, emit=) sockets/values.
    Creates a Principled material and remembers the channel sockets for baking."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    nb = NB(mat)
    ch = build(nb)
    out = nb.new("ShaderNodeOutputMaterial")
    out.name = "OUT"
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "BSDF"
    nb._in(bsdf.inputs['Base Color'], ch.get('color', (0.5, 0.5, 0.5)))
    nb._in(bsdf.inputs['Roughness'], ch.get('rough', 0.5))
    nb._in(bsdf.inputs['Metallic'], ch.get('metal', 0.0))
    if 'normal' in ch:
        nb._in(bsdf.inputs['Normal'], ch['normal'])
    if 'emit' in ch:
        nb._in(bsdf.inputs['Emission Color'], ch['emit'])
        bsdf.inputs['Emission Strength'].default_value = 1.0
    nb.Lk.new(bsdf.outputs[0], out.inputs['Surface'])
    # emission node used to route channels during bake
    em = nb.new("ShaderNodeEmission")
    em.name = "BAKE_EMIT"
    mat["_ch"] = 1
    _CH[mat.name] = ch
    return mat


_CH = {}


def _route(mat, channel):
    nt = mat.node_tree
    out = nt.nodes["OUT"]
    bsdf = nt.nodes["BSDF"]
    em = nt.nodes["BAKE_EMIT"]
    for l in list(out.inputs['Surface'].links):
        nt.links.remove(l)
    if channel == 'normal' or channel == 'ao':
        nt.links.new(bsdf.outputs[0], out.inputs['Surface'])
        return
    ch = _CH[mat.name]
    v = ch.get({'color': 'color', 'rough': 'rough', 'metal': 'metal', 'emit': 'emit'}[channel],
               (0, 0, 0) if channel == 'emit' else 0.0)
    for l in list(em.inputs['Color'].links):
        nt.links.remove(l)
    if isinstance(v, bpy.types.NodeSocket):
        nt.links.new(v, em.inputs['Color'])
    else:
        if np.isscalar(v):
            v = (v, v, v)
        em.inputs['Color'].default_value = (v[0], v[1], v[2], 1.0)
    em.inputs['Strength'].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs['Surface'])


def setup_cycles(samples=4):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    try:
        prefs.compute_device_type = 'HIP'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = (d.type == 'HIP' and 'RX' in d.name) or d.type == 'CPU' and False
        sc.cycles.device = 'GPU'
    except Exception as e:  # pragma: no cover
        print("GPU setup failed, CPU bake:", e)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False


def bake_object(ob, prefix, size, channels=('color', 'rough', 'metal', 'emit', 'normal', 'ao'),
                margin=16):
    """Bake procedural materials of ob into PNG maps named T_<prefix>_<suffix>.png.
    Returns dict channel -> image path. Normal is OpenGL (+Y) tangent space."""
    sc = bpy.context.scene
    setup_cycles()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    mats = [m for m in ob.data.materials]
    paths = {}
    suffix = {'color': 'BaseColor', 'rough': 'Roughness', 'metal': 'Metallic', 'emit': 'Emissive',
              'normal': 'Normal', 'ao': 'AO'}
    for chn in channels:
        noncolor = chn in ('rough', 'metal', 'normal', 'ao')
        img = bpy.data.images.new(f"T_{prefix}_{suffix[chn]}", size, size, alpha=False,
                                  float_buffer=False, is_data=noncolor)
        if chn == 'normal':
            img.generated_color = (0.5, 0.5, 1.0, 1.0)
        for m in mats:
            nt = m.node_tree
            tn = nt.nodes.get("BAKE_IMG") or nt.nodes.new("ShaderNodeTexImage")
            tn.name = "BAKE_IMG"
            tn.image = img
            nt.nodes.active = tn
            _route(m, chn)
        bk = sc.render.bake
        bk.margin = margin
        bk.use_clear = True
        bk.target = 'IMAGE_TEXTURES'
        if chn == 'normal':
            sc.cycles.samples = 4
            bk.normal_space = 'TANGENT'
            bk.normal_r, bk.normal_g, bk.normal_b = 'POS_X', 'POS_Y', 'POS_Z'
            bpy.ops.object.bake(type='NORMAL')
        elif chn == 'ao':
            sc.cycles.samples = 48
            bpy.ops.object.bake(type='AO')
        else:
            sc.cycles.samples = 4
            bpy.ops.object.bake(type='EMIT')
        p = os.path.join(TEX_DIR, f"T_{prefix}_{suffix[chn]}.png")
        img.filepath_raw = p
        img.file_format = 'PNG'
        img.save()
        paths[chn] = p
        print(f"  baked {chn} -> {p}", flush=True)
    for m in mats:
        _route(m, 'normal')
    return paths


def pack_orm(paths, prefix):
    """ORM = R:AO G:Roughness B:Metallic (Unreal-friendly), and a DirectX normal copy."""
    def load(p):
        im = bpy.data.images.load(p, check_existing=True)
        a = np.array(im.pixels[:], np.float32).reshape(im.size[1], im.size[0], 4)
        return im, a
    _, ao = load(paths['ao']) if 'ao' in paths else (None, None)
    imr, r = load(paths['rough'])
    _, m = load(paths['metal']) if 'metal' in paths else (None, None)
    h, w = r.shape[:2]
    out = np.ones((h, w, 4), np.float32)
    out[..., 0] = ao[..., 0] if ao is not None else 1.0
    out[..., 1] = r[..., 0]
    out[..., 2] = m[..., 0] if m is not None else 0.0
    img = bpy.data.images.new(f"T_{prefix}_ORM", w, h, alpha=False, is_data=True)
    img.pixels.foreach_set(out.ravel())
    p = os.path.join(TEX_DIR, f"T_{prefix}_ORM.png")
    img.filepath_raw = p
    img.file_format = 'PNG'
    img.save()
    paths['orm'] = p
    _, n = load(paths['normal'])
    n2 = n.copy()
    n2[..., 1] = 1.0 - n2[..., 1]
    img = bpy.data.images.new(f"T_{prefix}_Normal_DX", w, h, alpha=False, is_data=True)
    img.pixels.foreach_set(n2.ravel())
    p = os.path.join(TEX_DIR, f"T_{prefix}_Normal_DX.png")
    img.filepath_raw = p
    img.file_format = 'PNG'
    img.save()
    paths['normal_dx'] = p
    return paths


def final_material(name, paths, emissive_strength=1.0):
    """Image-texture material that glTF / FBX exporters understand."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])

    def tex(p, noncolor):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(p, check_existing=True)
        if noncolor:
            t.image.colorspace_settings.name = 'Non-Color'
        return t
    c = tex(paths['color'], False)
    nt.links.new(c.outputs[0], b.inputs['Base Color'])
    if 'orm' in paths:
        o = tex(paths['orm'], True)
        sp = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(o.outputs[0], sp.inputs[0])
        nt.links.new(sp.outputs[1], b.inputs['Roughness'])
        nt.links.new(sp.outputs[2], b.inputs['Metallic'])
    nm = tex(paths['normal'], True)
    nmn = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nm.outputs[0], nmn.inputs['Color'])
    nt.links.new(nmn.outputs[0], b.inputs['Normal'])
    if 'emit' in paths:
        e = tex(paths['emit'], False)
        nt.links.new(e.outputs[0], b.inputs['Emission Color'])
        b.inputs['Emission Strength'].default_value = emissive_strength
    return mat


def smart_uv(ob, angle=66.0, margin=0.003):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')


def tri_count(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    e = ob.evaluated_get(dg)
    m = e.to_mesh()
    m.calc_loop_triangles()
    n = len(m.loop_triangles)
    e.to_mesh_clear()
    return n


def apply_modifiers(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers):
        if m.type == 'ARMATURE':
            continue
        bpy.ops.object.modifier_apply(modifier=m.name)


# ----------------------------------------------------------------------------- animation
AX = {'x': Vector((1, 0, 0)), 'y': Vector((0, 1, 0)), 'z': Vector((0, 0, 1))}


def mirror_axis(v):
    return Vector((-v.x, v.y, -v.z))


def write_action(arm, name, n_frames, pose_fn, loop=True, paired=(), loc_bones=()):
    """pose_fn(f, phase)-> {bone: [(axis, angle), ...], '<bone>@loc': Vector}.
    Paired base names (no suffix) are applied to _L and mirrored to _R.
    Keys every frame 0..n_frames (inclusive; last == first for loops)."""
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    bones = arm.data.bones
    rest = {b.name: b.matrix_local.to_3x3() for b in bones}
    restq = {k: v.to_quaternion() for k, v in rest.items()}
    frames_q = {b.name: [] for b in bones}
    frames_l = {b: [] for b in loc_bones}
    for f in range(n_frames + 1):
        ph = 2 * math.pi * f / n_frames
        p = pose_fn(f, ph)
        expanded = {}
        for k, v in p.items():
            if k.endswith('@loc'):
                continue
            if k in paired:
                expanded[k + "_L"] = [(a, ang, False) for a, ang in v]
                expanded[k + "_R"] = [(a, ang, True) for a, ang in v]
            else:
                expanded[k] = [(a, ang, False) for a, ang in v]
        for b in bones:
            Q = Quaternion()
            for a, ang, mir in expanded.get(b.name, []):
                if isinstance(a, str) and a == 'b':
                    axv = (b.tail_local - b.head_local).normalized()
                    if mir:
                        ang = -ang
                else:
                    axv = AX[a].copy() if isinstance(a, str) else Vector(a)
                    if mir:
                        axv = mirror_axis(axv)
                Q = Quaternion(axv, ang) @ Q
            R = restq[b.name]
            ql = R.inverted() @ Q @ R
            lst = frames_q[b.name]
            if lst and lst[-1].dot(ql) < 0:
                ql.negate()
            lst.append(ql)
        for lb in loc_bones:
            d = p.get(lb + '@loc', Vector((0, 0, 0)))
            frames_l[lb].append(rest[lb].inverted() @ Vector(d))
    # write fcurves
    for bn, qs in frames_q.items():
        pb = arm.pose.bones[bn]
        pb.rotation_mode = 'QUATERNION'
        path = f'pose.bones["{bn}"].rotation_quaternion'
        for i in range(4):
            fc = act.fcurve_ensure_for_datablock(arm, path, index=i, group_name=bn)
            fc.keyframe_points.add(len(qs))
            co = np.zeros(len(qs) * 2)
            co[0::2] = np.arange(len(qs))
            co[1::2] = [q[i] for q in qs]
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", [1] * len(qs))  # LINEAR... (enum idx)
            fc.update()
    for bn, ls in frames_l.items():
        path = f'pose.bones["{bn}"].location'
        for i in range(3):
            fc = act.fcurve_ensure_for_datablock(arm, path, index=i, group_name=bn)
            fc.keyframe_points.add(len(ls))
            co = np.zeros(len(ls) * 2)
            co[0::2] = np.arange(len(ls))
            co[1::2] = [l[i] for l in ls]
            fc.keyframe_points.foreach_set("co", co)
            fc.update()
    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = n_frames
    act.use_cyclic = loop
    return act
