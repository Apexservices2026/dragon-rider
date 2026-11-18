"""Generate the opening fjord terrain in Blender (headless) and export it as FBX.

Run:  blender -b --python-exit-code 1 -P tools/blender/gen_fjord_terrain.py -- <out.fbx> [resolution]

Produces a 16 km x 16 km terrain: a winding sea fjord between steep ridged mountains,
opening to the sea (with islets) in the west. Vertex colours bake rock / moss / snow / wet
shore from height and slope, so the Unreal material only adds fine detail.
Blender units are metres; the FBX imports into Unreal at 1 m = 100 cm.
"""
import sys
import math
import bpy
import numpy as np
from mathutils import Vector, noise

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "fjord_terrain.fbx"
N = int(argv[1]) if len(argv) > 1 else 1025          # vertices per side
SIZE = 16000.0                                         # metres
SEED = 7

half = SIZE / 2
xs = np.linspace(-half, half, N)
ys = np.linspace(-half, half, N)
X, Y = np.meshgrid(xs, ys, indexing="xy")

def smoothstep(a, b, v):
    t = np.clip((v - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)

# --- Noise fields (mathutils noise is per-sample; ~1M samples is a few seconds each) ---
off = Vector((SEED * 13.1, SEED * 7.7, 0.37))
ridge = np.empty(N * N)
fbm = np.empty(N * N)
fine = np.empty(N * N)
fx, fy = X.ravel(), Y.ravel()
for i in range(N * N):
    px, py = fx[i], fy[i]
    p = Vector((px / 3400.0, py / 3400.0, 0.0)) + off
    ridge[i] = noise.ridged_multi_fractal(p, 0.95, 2.05, 7, 1.0, 2.1, noise_basis="PERLIN_NEW")
    q = Vector((px / 1500.0, py / 1500.0, 1.7)) + off
    fbm[i] = noise.fractal(q, 0.5, 2.0, 5, noise_basis="PERLIN_NEW")
    fine[i] = noise.noise(Vector((px / 180.0, py / 180.0, 4.2)), noise_basis="PERLIN_NEW")
ridge = ridge.reshape(N, N)
fbm = fbm.reshape(N, N)
fine = fine.reshape(N, N)

lo, hi = np.percentile(ridge, 2), np.percentile(ridge, 99.5)
m = np.clip((ridge - lo) / (hi - lo), 0, 1)
mountains = (m ** 1.35) * 1900.0 + fbm * 160.0 + 160.0   # tall, dramatic fjord walls

# --- Fjord channel: a winding centreline running west -> east ---
yc = 1700.0 * np.sin(X / 2600.0) + 550.0 * np.sin(X / 950.0 + 1.3)
width = 420.0 + 180.0 * np.sin(X / 1800.0 + 0.4) - 150.0 * smoothstep(3000, 7000, X)   # narrows inland
d = np.abs(Y - yc)
valley = smoothstep(width, width + 1500.0, d) ** 0.7                                 # steep fjord walls
shore_noise = fine * 40.0
h = -70.0 + (mountains + 70.0) * valley + shore_noise * valley * (1 - valley) * 4

# Open sea to the west with rocky islets.
sea = 1.0 - smoothstep(-6800.0, -3800.0, X)
islets = np.clip((fbm - 0.18) * 900.0, -80.0, 260.0) + fine * 25.0
h = h * (1 - sea) + np.where(islets > -60.0, islets, -80.0) * sea

# Tall rim on the north, south and east edges hides the end of the world.
rim = smoothstep(6300.0, 7900.0, np.maximum(np.abs(Y), np.where(X > 0, X, 0.0)))
h = h + rim * (650.0 + m * 450.0) * (1 - sea * 0.85)

# --- Vertex colours from height and slope (linear colour space) ---
gy, gx = np.gradient(h, ys[1] - ys[0], xs[1] - xs[0])
flat = 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)            # 1 = flat, 0 = vertical

rock = np.stack([0.075, 0.074, 0.078])
rock_dark = np.stack([0.035, 0.034, 0.036])
moss = np.stack([0.075, 0.095, 0.035])
heath = np.stack([0.11, 0.085, 0.045])
snow = np.stack([0.80, 0.84, 0.90])
wet = np.stack([0.03, 0.028, 0.026])

var = 0.8 + 0.4 * (fine * 0.5 + 0.5)
strata = 0.5 + 0.5 * np.sin(h / 23.0 + fbm * 6.0)
col = rock[None, None, :] * (var * (0.8 + 0.35 * strata))[..., None]
col = col * (1 - (1 - flat)[..., None] * 0.4) + rock_dark[None, None, :] * ((1 - flat) * 0.4)[..., None]

veg = smoothstep(0.82, 0.93, flat) * (1 - smoothstep(450.0, 750.0, h + fbm * 120.0)) * smoothstep(2.0, 12.0, h)
veg_col = moss[None, None, :] * (1 - fbm[..., None].clip(0, 1)) + heath[None, None, :] * fbm[..., None].clip(0, 1)
col = col * (1 - veg[..., None]) + veg_col * veg[..., None]

snow_line = 820.0 + fbm * 220.0 + fine * 40.0
snow_amt = smoothstep(snow_line - 60.0, snow_line + 80.0, h) * smoothstep(0.45, 0.7, flat)
snow_amt = np.maximum(snow_amt, smoothstep(1350.0, 1550.0, h) * smoothstep(0.25, 0.45, flat))
col = col * (1 - snow_amt[..., None]) + snow[None, None, :] * snow_amt[..., None]

shore = 1 - smoothstep(-5.0, 10.0, h)
col = col * (1 - shore[..., None]) + wet[None, None, :] * shore[..., None]

# --- Build mesh ---
verts = np.stack([X.ravel(), Y.ravel(), h.ravel()], axis=1)
idx = np.arange(N * N).reshape(N, N)
a = idx[:-1, :-1].ravel(); b = idx[:-1, 1:].ravel(); c = idx[1:, 1:].ravel(); e = idx[1:, :-1].ravel()
faces = np.stack([a, b, c, e], axis=1)

bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new("SM_FjordTerrain")
mesh.vertices.add(len(verts))
mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
mesh.loops.add(faces.size)
mesh.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
mesh.polygons.add(len(faces))
mesh.polygons.foreach_set("loop_start", (np.arange(len(faces)) * 4).astype(np.int32))
mesh.polygons.foreach_set("loop_total", np.full(len(faces), 4, dtype=np.int32))
mesh.update(calc_edges=True)
mesh.validate()

ca = mesh.color_attributes.new(name="Col", type="BYTE_COLOR", domain="POINT")
rgba = np.concatenate([col.reshape(-1, 3), np.ones((N * N, 1))], axis=1).astype(np.float32)
ca.data.foreach_set("color", rgba.ravel())   # BYTE_COLOR 'color' is stored as given; exported linearly below

uv = mesh.uv_layers.new(name="UVMap")
loop_v = faces.ravel()
uvs = np.stack([(verts[loop_v, 0] + half) / SIZE, (verts[loop_v, 1] + half) / SIZE], axis=1).astype(np.float32)
uv.data.foreach_set("uv", uvs.ravel())
mesh.shade_smooth()

obj = bpy.data.objects.new("SM_FjordTerrain", mesh)
bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

bpy.ops.export_scene.fbx(filepath=OUT, use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                         mesh_smooth_type="FACE", colors_type="LINEAR", add_leaf_bones=False, bake_anim=False)

stats = dict(min=float(h.min()), max=float(h.max()), water=float((h < 0).mean()), verts=len(verts))
print("FJORD_TERRAIN_OK", OUT, stats)

# Fjord centreline samples for placing the player start and set dressing.
for x in (-7000, -5000, -3000, 0, 3000):
    print("CENTRE", x, float(1700.0 * math.sin(x / 2600.0) + 550.0 * math.sin(x / 950.0 + 1.3)))
