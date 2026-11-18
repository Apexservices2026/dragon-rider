"""Build the Viking dragon rider procedurally (Blender 5.0, headless).

Run (after build_dragon.py):
  blender -b --factory-startup --python-exit-code 1 -P tools/blender/dragon/build_rider.py -- [--nobake] [--size 4096]

Seated Viking (~1.85 m standing): Gjermundbu-style spectacle helmet with mail aventail,
long braided beard, fur mantle over a mail shirt, leather belt, wool cloak, round painted
shield on the back, bearded axe at the left hip, both fists on the saddle horn.
The dragon (Dragon.blend) is loaded only as a fitting reference: legs are ray-cast against
its flank so they straddle the saddle; the cloak is kept above the dragon's back.
Rider origin = the dragon's Saddle seat point (attach at the Saddle bone).
Output: Saved/Generated/Dragon/Rider.blend (+ baked T_Rider_* textures).
"""
import sys
import os
import math
import time
import bpy
import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlib  # noqa: E402
from dlib import Acc, loft, chain_weights, wmix, sstep  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NOBAKE = "--nobake" in argv
TEX = int(argv[argv.index("--size") + 1]) if "--size" in argv else 4096
T0 = time.time()

# ------------------------------------------------------------------ dragon reference
bpy.ops.wm.open_mainfile(filepath=os.path.join(dlib.OUT_DIR, "Dragon.blend"))
drag = bpy.data.objects["Dragon"]
darm = bpy.data.objects["DragonRig"]
SEAT = darm.data.bones["Saddle"].head_local.copy()
dme = drag.data
dv = np.array([v.co[:] for v in dme.vertices])
# saddle horn knob: highest dragon vertex just ahead of the seat on the centre line
m = (dv[:, 0] > SEAT.x + 0.3) & (dv[:, 0] < SEAT.x + 0.8) & (np.abs(dv[:, 1]) < 0.12)
knob = dv[m][np.argmax(dv[m][:, 2])]
GRIP = Vector(knob) - SEAT + Vector((-0.035, 0, -0.10))
print("seat", tuple(SEAT), "grip (local)", tuple(GRIP))


def flank_y(x, z, side):
    """Dragon surface |y| at local (x, z) on the given side (ray from outside)."""
    o = Vector((x, side * 1.6, z)) + SEAT
    hit, loc, nrm, idx = drag.ray_cast(o, Vector((0, -side, 0)))
    return abs(loc.y) if hit else 0.0


def top_z(x, y):
    o = Vector((x, y, 4.0)) + SEAT
    hit, loc, nrm, idx = drag.ray_cast(o, Vector((0, 0, -1)))
    return (loc.z - SEAT.z) if hit else -1.0


# ------------------------------------------------------------------ fresh scene for the rider
keep_ref = {"flank": {}, "top": {}}
for o in list(bpy.data.objects):
    pass
# cache dragon queries before wiping
LEG_SAMPLES = {}
for side in (1, -1):
    for (x, z) in [(0.30, -0.02), (0.26, -0.20), (0.18, -0.40), (0.25, -0.48), (0.36, -0.50),
                   (0.08, 0.02), (0.18, -0.08)]:
        LEG_SAMPLES[(side, x, z)] = flank_y(x, z, side)
CAPE_TOP = {}
for x in np.linspace(-1.6, 0.3, 40):
    for y in np.linspace(-0.6, 0.6, 13):
        CAPE_TOP[(round(float(x), 4), round(float(y), 4))] = top_z(float(x), float(y))
print("flank samples", {k: round(v, 3) for k, v in LEG_SAMPLES.items()})

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 30


def cape_floor(x, y):
    xs = np.array(sorted({k[0] for k in CAPE_TOP}))
    ys = np.array(sorted({k[1] for k in CAPE_TOP}))
    xi = xs[np.argmin(np.abs(xs - x))]
    yi = ys[np.argmin(np.abs(ys - y))]
    return CAPE_TOP[(round(float(xi), 4), round(float(yi), 4))]


# ------------------------------------------------------------------ materials
def m_skin(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 40.0, 5.0).outputs['Factor']
    n2 = nb.noise(co, 6.0, 3.0).outputs['Factor']
    col = nb.mix(nb.maprange(n2, 0.3, 0.7), (0.32, 0.17, 0.11), (0.42, 0.22, 0.14))
    col = nb.mix(nb.math('MULTIPLY', n1, 0.3), col, (0.25, 0.10, 0.07))
    return dict(color=col, rough=nb.math('ADD', 0.45, nb.math('MULTIPLY', n1, 0.2)),
                normal=nb.bump(n1, 0.25, 0.004))


def m_hair(nb):
    co = nb.coord().outputs['Object']
    strands = nb.noise(nb.vscale(co, (60, 60, 6)), 4.0, 6.0, 0.7).outputs['Factor']
    n2 = nb.noise(co, 8.0, 2.0).outputs['Factor']
    col = nb.mix(nb.maprange(strands, 0.35, 0.7), (0.06, 0.022, 0.010), (0.22, 0.085, 0.03))
    col = nb.mix(nb.math('MULTIPLY', n2, 0.4), col, (0.30, 0.20, 0.12))
    return dict(color=col, rough=0.55, normal=nb.bump(strands, 0.8, 0.006))


def m_mail(nb):
    co = nb.coord().outputs['Object']
    rv = nb.voronoi(co, 110.0, 'F1', 0.0)
    d = rv.outputs['Distance']
    ring = nb.math('MULTIPLY', nb.maprange(d, 0.18, 0.32, 0.0, 1.0, 'SMOOTHSTEP'),
                   nb.maprange(d, 0.36, 0.48, 1.0, 0.0, 'SMOOTHSTEP'))
    rust = nb.noise(co, 5.0, 4.0).outputs['Factor']
    col = nb.mix(ring, (0.02, 0.018, 0.016), (0.32, 0.31, 0.30))
    col = nb.mix(nb.math('MULTIPLY', nb.maprange(rust, 0.55, 0.75), 0.6), col, (0.18, 0.08, 0.04))
    return dict(color=col, rough=nb.mixf(ring, 0.8, 0.35), metal=nb.math('MULTIPLY', ring, 0.9),
                normal=nb.bump(ring, 1.0, 0.003))


def m_wool(nb):
    co = nb.coord().outputs['Object']
    weave = nb.new("ShaderNodeTexWave", wave_type='BANDS', bands_direction='DIAGONAL')
    nb._in(weave.inputs['Vector'], co)
    weave.inputs['Scale'].default_value = 120.0
    n1 = nb.noise(co, 15.0, 4.0).outputs['Factor']
    col = nb.mix(nb.maprange(n1, 0.3, 0.7), (0.035, 0.05, 0.035), (0.07, 0.085, 0.055))
    col = nb.mix(nb.math('MULTIPLY', weave.outputs['Factor'], 0.25), col, (0.02, 0.025, 0.02))
    return dict(color=col, rough=0.85, normal=nb.bump(weave.outputs['Factor'], 0.25, 0.002))


def m_cloak(nb):
    co = nb.coord().outputs['Object']
    weave = nb.new("ShaderNodeTexWave", wave_type='BANDS', bands_direction='DIAGONAL')
    nb._in(weave.inputs['Vector'], co)
    weave.inputs['Scale'].default_value = 90.0
    n1 = nb.noise(co, 6.0, 4.0).outputs['Factor']
    edge = nb.attr("hem").outputs['Factor']
    col = nb.mix(nb.maprange(n1, 0.3, 0.7), (0.07, 0.008, 0.006), (0.14, 0.018, 0.012))
    col = nb.mix(nb.math('MULTIPLY', weave.outputs['Factor'], 0.2), col, (0.03, 0.004, 0.003))
    hem = nb.math('MULTIPLY', nb.maprange(edge, 0.955, 0.97), nb.maprange(edge, 0.99, 0.98))
    col = nb.mix(hem, col, (0.20, 0.12, 0.03))     # woven gold hem band
    return dict(color=col, rough=0.9, normal=nb.bump(weave.outputs['Factor'], 0.2, 0.002))


def m_leather(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 30.0, 6.0, 0.6).outputs['Factor']
    n2 = nb.noise(co, 5.0, 3.0).outputs['Factor']
    col = nb.mix(nb.maprange(n2, 0.3, 0.7), (0.06, 0.03, 0.015), (0.16, 0.085, 0.04))
    return dict(color=col, rough=nb.math('ADD', 0.45, nb.math('MULTIPLY', n1, 0.3)),
                normal=nb.bump(n1, 0.4, 0.004))


def m_fur(nb):
    co = nb.coord().outputs['Object']
    strands = nb.noise(nb.vscale(co, (25, 25, 4)), 6.0, 8.0, 0.75, 1.5).outputs['Factor']
    clump = nb.voronoi(co, 22.0, 'F1').outputs['Distance']
    n2 = nb.noise(co, 4.0, 3.0).outputs['Factor']
    h = nb.math('ADD', nb.math('MULTIPLY', strands, 0.7), nb.math('MULTIPLY', clump, 0.5))
    col = nb.ramp(nb.math('MULTIPLY', h, 0.9), [(0.0, (0.015, 0.012, 0.01)), (0.45, (0.11, 0.085, 0.06)),
                                              (0.8, (0.30, 0.25, 0.19)), (1.0, (0.45, 0.40, 0.33))])
    col = nb.mix(nb.math('MULTIPLY', n2, 0.5), col, (0.08, 0.06, 0.045))
    return dict(color=col, rough=0.95, normal=nb.bump(h, 1.0, 0.012))


def m_iron(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 25.0, 5.0).outputs['Factor']
    n2 = nb.noise(co, 3.0, 3.0).outputs['Factor']
    col = nb.mix(nb.maprange(n2, 0.45, 0.75), (0.22, 0.21, 0.20), (0.10, 0.06, 0.035))
    col = nb.mix(nb.math('MULTIPLY', n1, 0.3), col, (0.05, 0.05, 0.05))
    return dict(color=col, rough=nb.math('ADD', 0.28, nb.math('MULTIPLY', n1, 0.35)), metal=0.95,
                normal=nb.bump(n1, 0.35, 0.003))


def m_wood(nb):
    """Shield boards / axe haft. Shield face paint uses attribute 'shp' (r, angle, face)."""
    co = nb.coord().outputs['Object']
    shp = nb.attr("shp").outputs['Vector']
    r, ang, face = nb.sep(shp)
    grain = nb.noise(nb.vscale(co, (4, 4, 60)), 3.0, 6.0, 0.6, 2.0).outputs['Factor']
    wood = nb.mix(nb.maprange(grain, 0.3, 0.7), (0.10, 0.05, 0.02), (0.26, 0.14, 0.06))
    seg = nb.math('MODULO', nb.math('FLOOR', nb.math('MULTIPLY', nb.math('ADD', ang, 3.14159), 8 / 6.28318)), 2.0)
    paint = nb.mix(seg, (0.40, 0.33, 0.20), (0.22, 0.012, 0.008))
    band = nb.math('MULTIPLY', nb.maprange(r, 0.42, 0.46), nb.maprange(r, 0.58, 0.54))
    paint = nb.mix(band, paint, (0.02, 0.02, 0.02))
    wear = nb.maprange(nb.noise(co, 9.0, 5.0).outputs['Factor'], 0.55, 0.7)
    paint = nb.mix(wear, paint, wood)
    col = nb.mix(face, wood, paint)
    return dict(color=col, rough=0.7, normal=nb.bump(grain, 0.4, 0.003))


MATS = [dlib.pbr_material("SRC_R_" + n, f) for n, f in
        [("Skin", m_skin), ("Hair", m_hair), ("Mail", m_mail), ("Wool", m_wool), ("Cloak", m_cloak),
         ("Leather", m_leather), ("Fur", m_fur), ("Iron", m_iron), ("Wood", m_wood)]]
SKIN, HAIR, MAIL, WOOL, CLOAK, LEATH, FUR, IRON, WOOD = range(9)

A = Acc(vec=("shp",))
BONES = {}


def bone(n, h, t, par):
    BONES[n] = (Vector(h), Vector(t), par)


def V(*a):
    return np.array(a, float)


# ------------------------------------------------------------------ skeleton (local, origin = seat)
lean = math.radians(18)
def spine_pt(h):   # point at height h above seat along the forward-leaning spine
    return V(0.02 + math.sin(lean) * h, 0, 0.10 + math.cos(lean) * h)


P_PELVIS, P_SP1, P_SP2, P_CHEST, P_NECK, P_HEAD, P_TOP = (spine_pt(h) for h in (0.0, 0.14, 0.30, 0.44, 0.60, 0.68, 0.93))
bone("RiderRoot", (0, 0, 0), (0, 0.2, 0), None)   # identity rest frame (attach-friendly)
bone("Pelvis", P_PELVIS, P_SP1, "RiderRoot")
bone("Spine01", P_SP1, P_SP2, "Pelvis")
bone("Spine02", P_SP2, P_CHEST, "Spine01")
bone("Chest", P_CHEST, P_NECK, "Spine02")
bone("Neck", P_NECK, P_HEAD, "Chest")
bone("Head", P_HEAD, P_TOP, "Neck")
SP_CHAIN = ["Pelvis", "Spine01", "Spine02", "Chest", "Neck", "Head"]


def two_bone(a, target, l1, l2, pole):
    a, target, pole = np.asarray(a), np.asarray(target), np.asarray(pole)
    d = target - a
    dist = min(np.linalg.norm(d), (l1 + l2) * 0.999)
    dn = d / np.linalg.norm(d)
    cosA = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
    ang = math.acos(max(-1, min(1, cosA)))
    pv = pole - a
    pv = pv - np.dot(pv, dn) * dn
    pv /= np.linalg.norm(pv)
    elbow = a + dn * math.cos(ang) * l1 + pv * math.sin(ang) * l1
    return elbow, a + dn * dist


# ------------------------------------------------------------------ torso, skirt, belt
def chainw(L, joints, names, blend=0.35):
    return chain_weights(L, joints, names, blend=blend)


hs = [0.0, 0.14, 0.30, 0.44, 0.60, 0.68]
torso_rows = []
for h, w, d in [(-0.06, 0.16, 0.13), (0.0, 0.185, 0.14), (0.12, 0.175, 0.13), (0.28, 0.20, 0.145),
                (0.42, 0.25, 0.16), (0.52, 0.26, 0.145), (0.58, 0.16, 0.10), (0.63, 0.07, 0.07)]:
    p = spine_pt(h)
    torso_rows.append((p[0], 0, p[2], w, d))
info = loft(A, torso_rows, 40, 28, up=(1, 0, 0), mat=MAIL)
st = A.n - (40 * 28 + 2)
Jl = [0.0] + [h - (-0.06) for h in hs[1:]] + [10.0]
for i in range(40):
    hh = info['L'][i] - 0.0
    w = chain_weights(info['L'][i], [info['L'][0] + (h + 0.06) for h in hs], SP_CHAIN, blend=0.4)
    for j in range(28):
        A.W[st + i * 28 + j] = w
A.W[st + 40 * 28] = {"Pelvis": 1.0}
A.W[st + 40 * 28 + 1] = {"Neck": 1.0}
# mail skirt (split front/back by the saddle) - short flared tube
sk_rows = [(spine_pt(0.12)[0], 0, spine_pt(0.12)[2], 0.18, 0.135), (0.03, 0, 0.06, 0.22, 0.17), (0.04, 0, -0.04, 0.25, 0.19)]
loft(A, sk_rows, 10, 28, up=(1, 0, 0), cap0=False, cap1=False, mat=MAIL,
     weight_fn=lambda t, L: wmix((1 - t, {"Spine01": 1.0}), (t, {"Pelvis": 1.0})))
# belt + buckle
bp = spine_pt(0.13)
belt = []
for a in np.linspace(0, 2 * math.pi, 41)[:-1]:
    belt.append((bp[0] + 0.145 * math.cos(a) * 1.04, 0.183 * math.sin(a) * 1.04, bp[2]))
belt_rows = [tuple(p) + (0.012, 0.035) for p in belt] + [tuple(belt[0]) + (0.012, 0.035)]
loft(A, belt_rows, 80, 8, up=(0, 0, 1), cap0=False, cap1=False, mat=LEATH,
     weight_fn=lambda t, L: {"Spine01": 0.5, "Pelvis": 0.5})
loft(A, [(bp[0] + 0.155, 0, bp[2] - 0.03, 0.03, 0.01), (bp[0] + 0.158, 0, bp[2] + 0.03, 0.03, 0.01)],
     4, 10, up=(1, 0, 0), mat=IRON, weight_fn=lambda t, L: {"Spine01": 0.5, "Pelvis": 0.5})

# ------------------------------------------------------------------ head, helmet, beard
hc = spine_pt(0.78)          # head centre
face_fwd = V(math.cos(math.radians(-8)), 0, math.sin(math.radians(-8)))   # looking slightly up from lean
head_rows = []
for dz, w, d, fx in [(-0.17, 0.06, 0.06, -0.01), (-0.11, 0.065, 0.075, 0.0), (-0.06, 0.085, 0.10, 0.02),
                     (0.0, 0.09, 0.105, 0.02), (0.06, 0.088, 0.10, 0.01), (0.11, 0.075, 0.085, 0.0),
                     (0.15, 0.01, 0.01, 0.0)]:
    head_rows.append((hc[0] + fx, 0, hc[2] + dz, w, d))
loft(A, head_rows, 26, 24, up=(1, 0, 0), mat=SKIN, weight_fn=lambda t, L: {"Head": 1.0} if t > 0.15 else {"Head": 0.6, "Neck": 0.4})
# nose + brows
loft(A, [(hc[0] + 0.105, 0, hc[2] + 0.025, 0.012, 0.012), (hc[0] + 0.125, 0, hc[2] - 0.015, 0.018, 0.02),
         (hc[0] + 0.12, 0, hc[2] - 0.03, 0.01, 0.01)], 8, 10, up=(0, 0, 1), mat=SKIN,
     weight_fn=lambda t, L: {"Head": 1.0})
for sg in (1, -1):
    # eyes (dark, deep-set) under the spectacle guard
    e = hc + V(0.095, sg * 0.036, 0.02)
    loft(A, [tuple(e - V(0.008, 0, 0)) + (0.0005, 0.0005), tuple(e) + (0.011, 0.011), tuple(e + V(0.01, 0, 0)) + (0.0005, 0.0005)],
         6, 10, up=(0, 0, 1), mat=HAIR, weight_fn=lambda t, L: {"Head": 1.0})
    loft(A, [(hc[0] + 0.1, sg * 0.012, hc[2] + 0.045, 0.006, 0.008), (hc[0] + 0.097, sg * 0.045, hc[2] + 0.05, 0.007, 0.01),
             (hc[0] + 0.085, sg * 0.07, hc[2] + 0.04, 0.004, 0.006)], 8, 8, up=(1, 0, 0), mat=HAIR,
         weight_fn=lambda t, L: {"Head": 1.0})
    # moustache
    loft(A, [(hc[0] + 0.115, 0, hc[2] - 0.04, 0.01, 0.01), (hc[0] + 0.11, sg * 0.03, hc[2] - 0.05, 0.012, 0.012),
             (hc[0] + 0.095, sg * 0.05, hc[2] - 0.09, 0.007, 0.007)], 10, 8, up=(1, 0, 0), mat=HAIR,
         weight_fn=lambda t, L: {"Head": 1.0})

# helmet dome
hb = hc + V(0.0, 0, 0.045)
dome = []
for dz, s in [(0.0, 1.0), (0.04, 0.97), (0.08, 0.86), (0.115, 0.62), (0.135, 0.3), (0.142, 0.01)]:
    dome.append((hb[0] + 0.012, 0, hb[2] + dz, 0.102 * s, 0.118 * s))
loft(A, dome, 24, 32, up=(1, 0, 0), cap0=False, mat=IRON, weight_fn=lambda t, L: {"Head": 1.0})
# brow band, crest ridge and spectacle guard
band = [(hb[0] + 0.012 + 0.121 * math.cos(a), 0.105 * math.sin(a), hb[2] + 0.005) for a in np.linspace(0, 2 * math.pi, 37)]
loft(A, [tuple(p) + (0.008, 0.014) for p in band], 72, 8, up=(0, 0, 1), cap0=False, cap1=False, mat=IRON,
     weight_fn=lambda t, L: {"Head": 1.0})
crest = [(hb[0] + 0.012 + 0.12 * math.cos(a), 0, hb[2] + 0.142 * math.sin(a) + 0.002) for a in np.linspace(0.05, math.pi - 0.05, 15)]
loft(A, [tuple(p) + (0.007, 0.012) for p in crest], 30, 8, up=(0, 1, 0), cap0=True, cap1=True, mat=IRON,
     weight_fn=lambda t, L: {"Head": 1.0})
for sg in (1, -1):
    ec = hc + V(0.112, sg * 0.038, 0.018)
    ring = [tuple(ec + V(0.004 * math.sin(a), sg * 0.028 * math.cos(a), 0.024 * math.sin(a))) for a in np.linspace(0, 2 * math.pi, 21)]
    loft(A, [r + (0.006, 0.006) for r in ring], 40, 8, up=(1, 0, 0), cap0=False, cap1=False, mat=IRON,
         weight_fn=lambda t, L: {"Head": 1.0})
loft(A, [(hc[0] + 0.128, 0, hc[2] + 0.05, 0.008, 0.006), (hc[0] + 0.132, 0, hc[2] + 0.0, 0.009, 0.006),
         (hc[0] + 0.138, 0, hc[2] - 0.035, 0.007, 0.005)], 10, 8, up=(1, 0, 0), mat=IRON,
     weight_fn=lambda t, L: {"Head": 1.0})
# mail aventail hanging from the helmet rim at the back and sides
NU, NVv = 26, 8
P = np.zeros((NVv, NU, 3))
for vi, v in enumerate(np.linspace(0, 1, NVv)):
    for ui, a in enumerate(np.linspace(math.radians(70), math.radians(290), NU)):
        rr = 1.0 + 0.35 * v
        P[vi, ui] = (hb[0] + 0.006 + 0.122 * rr * math.cos(a) - 0.03 * v, 0.106 * rr * math.sin(a), hb[2] - 0.13 * v)
A.grid(P, mat=MAIL, weights=[wmix((1 - v * 0.7, {"Head": 1.0}), (v * 0.7, {"Neck": 1.0})) for v in np.linspace(0, 1, NVv) for _ in range(NU)])

# beard: full mass + long braid with twisted strands
bc = hc + V(0.085, 0, -0.07)
beard_rows = [(bc[0] - 0.02, 0, bc[2] + 0.03, 0.075, 0.04), (bc[0] + 0.01, 0, bc[2] - 0.03, 0.078, 0.05),
              (bc[0] + 0.03, 0, bc[2] - 0.10, 0.06, 0.045), (bc[0] + 0.045, 0, bc[2] - 0.16, 0.04, 0.035),
              (bc[0] + 0.05, 0, bc[2] - 0.20, 0.03, 0.028)]
loft(A, beard_rows, 24, 20, up=(1, 0, 0), mat=HAIR, cap0=True, cap1=False,
     section=lambda t, th, L: 1.0 + 0.10 * abs(math.sin(5 * th + t * 9)),
     weight_fn=lambda t, L: wmix((1 - t, {"Head": 1.0}), (t, {"Beard": 1.0})))
braid0 = V(bc[0] + 0.05, 0, bc[2] - 0.19)
braid_rows = []
for k, t in enumerate(np.linspace(0, 1, 8)):
    braid_rows.append((braid0[0] + 0.03 * t - 0.04 * t * t, 0.006 * math.sin(t * 6), braid0[2] - 0.32 * t,
                       0.028 * (1 - 0.55 * t), 0.024 * (1 - 0.55 * t)))
loft(A, braid_rows, 60, 16, up=(1, 0, 0), mat=HAIR, cap0=False, cap1=True,
     section=lambda t, th, L: 1.0 + 0.22 * abs(math.sin(1.5 * th + L * 95.0)),
     weight_fn=lambda t, L: {"Beard": 1.0})
# iron beard ring
loft(A, [tuple(braid0 + V(0.012, 0, -0.20)) + (0.016, 0.016), tuple(braid0 + V(0.010, 0, -0.225)) + (0.016, 0.016)],
     4, 12, up=(1, 0, 0), mat=IRON, weight_fn=lambda t, L: {"Beard": 1.0})
bone("Beard", tuple(bc + V(0.0, 0, -0.02)), tuple(braid0 + V(0.0, 0, -0.30)), "Head")

# ------------------------------------------------------------------ arms + fists
for sg, sfx in ((1, "_L"), (-1, "_R")):
    clav0 = spine_pt(0.53) + V(0.0, sg * 0.03, 0)
    sh = spine_pt(0.52) + V(-0.01, sg * 0.235, -0.02)
    hand = np.array(GRIP) + V(-0.0, sg * 0.05, 0.0)
    wrist_t = hand + V(-0.06, sg * 0.02, 0.03)
    elbow, wr = two_bone(sh, wrist_t, 0.31, 0.28, sh + V(-0.1, sg * 0.35, -0.25))
    bone("Clavicle" + sfx, clav0, sh, "Chest")
    bone("UpperArm" + sfx, sh, elbow, "Clavicle" + sfx)
    bone("Forearm" + sfx, elbow, wr, "UpperArm" + sfx)
    bone("Hand" + sfx, wr, hand + V(0.03, 0, 0), "Forearm" + sfx)
    rows = [tuple(clav0) + (0.06, 0.06), tuple(sh) + (0.075, 0.075), tuple((sh + elbow) / 2) + (0.058, 0.062),
            tuple(elbow) + (0.05, 0.05), tuple(elbow + (wr - elbow) * 0.55) + (0.048, 0.045), tuple(wr) + (0.037, 0.03)]
    info = loft(A, rows, 40, 16, up=(0, 0, 1), mat=MAIL)
    J = [info['ctrlL'][k] for k in (0, 1, 3, 5)]
    names = ["Chest", "UpperArm" + sfx, "Forearm" + sfx]
    st = A.n - (40 * 16 + 2)
    for i in range(40):
        w = chain_weights(info['L'][i], J, names, blend=0.3)
        if info['L'][i] < J[1] + 0.05:
            w = wmix((0.6, w), (0.4, {"Clavicle" + sfx: 1.0}))
        for j in range(16):
            A.W[st + i * 16 + j] = w
    A.W[st + 640] = {"Chest": 1.0}
    A.W[st + 641] = {"Forearm" + sfx: 1.0}
    # leather bracer over the forearm
    b0, b1 = elbow + (wr - elbow) * 0.35, wr + (wr - elbow) * 0.02
    loft(A, [tuple(b0) + (0.054, 0.052), tuple((b0 + b1) / 2) + (0.05, 0.047), tuple(b1) + (0.042, 0.036)], 10, 16,
         up=(0, 0, 1), cap0=False, cap1=False, mat=LEATH, weight_fn=lambda t, L, s=sfx: {"Forearm" + s: 1.0})
    # fist (leather glove) wrapped round the horn post
    fd = hand - wr
    fd /= np.linalg.norm(fd)
    loft(A, [tuple(wr) + (0.035, 0.028), tuple(hand - fd * 0.02) + (0.048, 0.04), tuple(hand + fd * 0.035) + (0.045, 0.042),
             tuple(hand + fd * 0.06) + (0.02, 0.02)], 14, 16, up=(0, 0, 1), mat=LEATH,
         weight_fn=lambda t, L, s=sfx: {"Hand" + s: 1.0})
    th = hand + V(0.01, -sg * 0.02, 0.035)
    loft(A, [tuple(hand + V(-0.02, 0, 0.02)) + (0.015, 0.015), tuple(th) + (0.013, 0.013), tuple(th + V(0.02, -sg * 0.015, 0.0)) + (0.01, 0.01)],
         8, 10, up=(0, 0, 1), mat=LEATH, weight_fn=lambda t, L, s=sfx: {"Hand" + s: 1.0})

# ------------------------------------------------------------------ legs straddling the saddle
for sg, sfx in ((1, "_L"), (-1, "_R")):
    hip = V(0.02, sg * 0.10, 0.08)

    def out(x, z, r, extra=0.0):
        return max(LEG_SAMPLES.get((sg, x, z), 0.0) + r + 0.01 + extra, 0.0)
    knee = V(0.30, sg * out(0.30, -0.02, 0.06, 0.02), -0.02)
    ankle = V(0.18, sg * out(0.18, -0.40, 0.05), -0.40)
    toe = V(0.36, sg * out(0.36, -0.50, 0.04), -0.50)
    mid_t = (hip + knee) / 2 + V(0, sg * 0.03, 0.03)
    s_shin = (knee + ankle) / 2
    s_shin[1] = sg * out(0.26, -0.20, 0.055)
    bone("Thigh" + sfx, hip, knee, "Pelvis")
    bone("Shin" + sfx, knee, ankle, "Thigh" + sfx)
    bone("Foot" + sfx, ankle, toe, "Shin" + sfx)
    rows = [tuple(hip + V(0, -sg * 0.04, 0.02)) + (0.10, 0.10), tuple(mid_t) + (0.085, 0.09), tuple(knee) + (0.062, 0.065),
            tuple(s_shin) + (0.058, 0.06), tuple(ankle) + (0.046, 0.05)]
    info = loft(A, rows, 36, 18, up=(1, 0, 0), mat=WOOL)
    J = [info['ctrlL'][k] for k in (0, 2, 4)]
    st = A.n - (36 * 18 + 2)
    for i in range(36):
        w = chain_weights(info['L'][i], J, ["Thigh" + sfx, "Shin" + sfx], blend=0.3)
        if info['L'][i] < 0.12:
            g = info['L'][i] / 0.12
            w = wmix((1 - g, {"Pelvis": 1.0}), (g, w))
        for j in range(18):
            A.W[st + i * 18 + j] = w
    A.W[st + 648] = {"Pelvis": 1.0}
    A.W[st + 649] = {"Shin" + sfx: 1.0}
    # leg wraps + boot
    loft(A, [tuple(knee + (ankle - knee) * 0.15) + (0.064, 0.066), tuple(s_shin) + (0.063, 0.065),
             tuple(ankle + V(0, 0, 0.05)) + (0.054, 0.056)], 10, 18, up=(1, 0, 0), cap0=False, cap1=False,
         mat=LEATH, weight_fn=lambda t, L, s=sfx: {"Shin" + s: 1.0},
         section=lambda t, th, L: 1.0 + 0.06 * abs(math.sin(L * 70 + th * 0.5)))
    fd = toe - ankle
    loft(A, [tuple(ankle + V(0, 0, 0.06)) + (0.055, 0.058), tuple(ankle) + (0.05, 0.06), tuple(ankle + fd * 0.55 + V(0, 0, -0.015)) + (0.045, 0.035),
             tuple(toe) + (0.035, 0.028), tuple(toe + fd * 0.08) + (0.01, 0.01)], 18, 16, up=(0, 0, 1), mat=LEATH,
         weight_fn=lambda t, L, s=sfx: {"Foot" + s: 1.0} if t > 0.2 else {"Shin" + s: 0.5, "Foot" + s: 0.5})

# ------------------------------------------------------------------ fur mantle
mc = spine_pt(0.565)
ring = []
for a in np.linspace(-math.pi, math.pi, 33):
    rx = 0.17 if math.cos(a) > 0 else 0.20
    ring.append((mc[0] + rx * math.cos(a) * 0.95 - 0.01, 0.255 * math.sin(a), mc[2] - 0.03 * math.cos(a) + 0.02 * (1 - abs(math.sin(a)))))
ring.append(ring[1])
loft(A, [tuple(p) + (0.075, 0.085) for p in ring], 90, 16, up=(0, 0, 1), cap0=False, cap1=False, mat=FUR,
     section=lambda t, th, L: 1.0 + 0.18 * abs(math.sin(L * 37.0 + 3 * th)) * abs(math.sin(L * 13.0)),
     weight_fn=lambda t, L: {"Chest": 0.85, "Neck": 0.15})
# fur over the shoulders (pauldron-like lumps)
for sg, sfx in ((1, "_L"), (-1, "_R")):
    s0 = spine_pt(0.53) + V(-0.01, sg * 0.23, 0.0)
    loft(A, [tuple(s0 + V(-0.08, -sg * 0.04, 0.02)) + (0.06, 0.06), tuple(s0 + V(0.0, sg * 0.02, 0.04)) + (0.095, 0.075),
             tuple(s0 + V(0.06, sg * 0.04, -0.02)) + (0.05, 0.05)], 14, 16, up=(0, 0, 1), mat=FUR,
         section=lambda t, th, L: 1.0 + 0.15 * abs(math.sin(L * 50.0 + 4 * th)),
         weight_fn=lambda t, L, s=sfx: {"Chest": 0.6, "Clavicle" + s: 0.4})

# ------------------------------------------------------------------ cloak / cape (streams back over the dragon)
NU, NVc = 22, 34
P = np.zeros((NVc, NU, 3))
Wt, hem = [], np.zeros((NVc, NU))
CAPE_N = 4
V_DROP = 0.36          # first part hangs down the back (under the shield), then streams back


def back_depth(h):
    return float(np.interp(h, [0.0, 0.12, 0.28, 0.42, 0.52, 0.58], [0.14, 0.13, 0.145, 0.155, 0.14, 0.10]))


for vi, v in enumerate(np.linspace(0, 1, NVc)):
    for ui, u in enumerate(np.linspace(-1, 1, NU)):
        a = u * math.radians(80)
        if v <= V_DROP:
            s_ = v / V_DROP
            h = 0.55 - 0.45 * s_
            pc = spine_pt(h)
            x = pc[0] - (back_depth(h) + 0.022) * math.cos(a)
            y = (0.215 + 0.03 * s_) * math.sin(a)
            z = pc[2] + 0.02 * (1 - s_)
        else:
            s2 = (v - V_DROP) / (1 - V_DROP)
            pc = spine_pt(0.10)
            x = pc[0] - (back_depth(0.10) + 0.022) * math.cos(a) - 1.05 * s2 - 0.2 * s2 * s2
            y = 0.245 * math.sin(a) * (1 + 0.85 * s2)
            z = pc[2] - 0.20 * s2
            z += 0.03 * math.sin(u * 7 + s2 * 9) * s2
            fl = cape_floor(x, y)
            z = max(z, fl + 0.07 + 0.04 * (1 - abs(u)))
        P[vi, ui] = (x, y, z)
        cv = max(0.0, (v - 0.30) / 0.70)          # cape bones cover the free part
        k = cv * CAPE_N
        if v < 0.30:
            w = {"Chest": 1.0} if v < 0.2 else wmix((1 - (v - 0.2) / 0.1, {"Chest": 1.0}), ((v - 0.2) / 0.1, {"Cape01": 0.5, "Chest": 0.5}))
        else:
            i0 = min(int(k), CAPE_N - 1)
            f = k - i0
            w = {f"Cape{i0 + 1:02d}": 1 - f}
            if i0 + 1 < CAPE_N:
                w[f"Cape{i0 + 2:02d}"] = f
            if v < 0.36:
                w = wmix((0.5, w), (0.5, {"Chest": 1.0}))
        Wt.append(w)
        hem[vi, ui] = max(v, abs(u))
A.grid(P, mat=CLOAK, weights=Wt, attrs={"hem": hem.ravel()})
cen = P[:, NU // 2]
for i in range(CAPE_N):
    a_ = cen[int((0.30 + 0.70 * i / CAPE_N) * (NVc - 1))]
    b_ = cen[int((0.30 + 0.70 * (i + 1) / CAPE_N) * (NVc - 1))]
    bone(f"Cape{i + 1:02d}", a_, b_, "Chest" if i == 0 else f"Cape{i:02d}")
# cloak brooch at the right shoulder
br = spine_pt(0.56) + V(0.12, -0.16, 0.0)
loft(A, [tuple(br + V(-0.01, 0, 0)) + (0.03, 0.03), tuple(br + V(0.012, 0, 0)) + (0.03, 0.03)], 4, 14,
     up=(0, 0, 1), mat=IRON, weight_fn=lambda t, L: {"Chest": 1.0})

# ------------------------------------------------------------------ round shield on the back
sh_c = spine_pt(0.36) + V(-0.235, 0, 0.0)
sh_n = V(-math.cos(math.radians(28)), 0, math.sin(math.radians(28)))   # facing back/up
sh_u = np.cross(sh_n, V(0, 1, 0))
sh_u /= np.linalg.norm(sh_u)
sh_v = np.cross(sh_n, sh_u)
R_SH, NRr, NA = 0.40, 14, 48
verts, faces, shp = [], [], []
for side in (0, 1):
    off = sh_n * (0.012 if side == 0 else -0.012)
    for ri, r in enumerate(np.linspace(0.0, R_SH, NRr)):
        for ai, a in enumerate(np.linspace(0, 2 * math.pi, NA, endpoint=False)):
            dome_h = 0.015 * (1 - (r / R_SH) ** 2) if side == 0 else 0.0
            p = sh_c + off + sh_n * dome_h + sh_u * r * math.cos(a) + sh_v * r * math.sin(a)
            verts.append(p)
            shp.append((r / R_SH, math.atan2(math.sin(a), math.cos(a)), 1.0 if side == 0 else 0.0))
ring_n = NA
for side in (0, 1):
    base = side * NRr * NA
    for ri in range(NRr - 1):
        for ai in range(NA):
            a2 = (ai + 1) % NA
            f = [base + ri * NA + ai, base + ri * NA + a2, base + (ri + 1) * NA + a2, base + (ri + 1) * NA + ai]
            faces.append(f if side == 0 else f[::-1])
o0, o1 = (NRr - 1) * NA, NRr * NA + (NRr - 1) * NA
for ai in range(NA):
    a2 = (ai + 1) % NA
    faces.append([o0 + ai, o1 + ai, o1 + a2, o0 + a2])
A.add(verts, faces, mat=WOOD, weights={"Chest": 1.0}, attrs={"shp": np.array(shp)})
# boss + rim
loft(A, [tuple(sh_c + sh_n * 0.02) + (0.075, 0.075), tuple(sh_c + sh_n * 0.06) + (0.06, 0.06),
         tuple(sh_c + sh_n * 0.085) + (0.03, 0.03), tuple(sh_c + sh_n * 0.09) + (0.002, 0.002)],
     10, 24, up=tuple(sh_u), cap0=True, cap1=False, mat=IRON, weight_fn=lambda t, L: {"Chest": 1.0})
rim = [tuple(sh_c + sh_u * R_SH * math.cos(a) + sh_v * R_SH * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 49)]
loft(A, [r + (0.014, 0.018) for r in rim], 96, 8, up=tuple(sh_n), cap0=False, cap1=False, mat=LEATH,
     weight_fn=lambda t, L: {"Chest": 1.0})
# strap across the chest (baldric) from left shoulder to right hip
loft(A, [tuple(spine_pt(0.52) + V(0.10, 0.16, 0.02)) + (0.03, 0.008), tuple(spine_pt(0.36) + V(0.165, 0.0, 0.0)) + (0.03, 0.008),
         tuple(spine_pt(0.18) + V(0.14, -0.15, 0.0)) + (0.03, 0.008)], 18, 6, up=(1, 0, 0), cap0=False, cap1=False,
     mat=LEATH, weight_fn=lambda t, L: {"Chest": 1 - t * 0.6, "Spine01": t * 0.6})

# ------------------------------------------------------------------ bearded axe at the left hip
ax_top = V(0.12, 0.215, 0.30)
ax_bot = V(-0.12, 0.27, -0.33)
hd = ax_bot - ax_top
hd /= np.linalg.norm(hd)
loft(A, [tuple(ax_top + hd * -0.05) + (0.016, 0.016), tuple(ax_top + hd * 0.3) + (0.017, 0.017), tuple(ax_bot) + (0.019, 0.019)],
     20, 10, up=(0, 1, 0), mat=WOOD, weight_fn=lambda t, L: {"Pelvis": 1.0})
# head profile in (a: blade direction forward, b: along haft up)
blade_dir = np.cross(hd, V(0, 1, 0))
blade_dir /= np.linalg.norm(blade_dir)
if blade_dir[0] < 0:
    blade_dir = -blade_dir
prof = [(-0.03, 0.035), (0.04, 0.03), (0.12, 0.045), (0.19, 0.075), (0.205, 0.03), (0.2, -0.04),
        (0.17, -0.12), (0.13, -0.13), (0.11, -0.06), (0.06, -0.03), (-0.03, -0.035)]
up_haft = -hd
side_n = V(0, 1, 0)
verts = []
nP = len(prof)
for s in (1, -1):
    for a, b in prof:
        th = 0.018 * (1 - max(0.0, a) / 0.21) + 0.0015
        verts.append(ax_top + up_haft * (b - 0.02) + blade_dir * a + side_n * s * th)
faces = [list(range(nP)), list(range(2 * nP - 1, nP - 1, -1))]
for i in range(nP):
    j = (i + 1) % nP
    faces.append([i, j, nP + j, nP + i])
A.add(verts, faces, mat=IRON, weights={"Pelvis": 1.0})

# ------------------------------------------------------------------ build + rig
rider = A.build("Rider", MATS)
# triangulate the axe n-gons etc. happens on export; subdivide nothing (budget)
print(f"rider geometry {time.time() - T0:.1f}s verts {len(rider.data.vertices)}")
arm_d = bpy.data.armatures.new("RiderRig")
arm = bpy.data.objects.new("RiderRig", arm_d)
sc.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
for n, (h, t, par) in BONES.items():
    eb = arm_d.edit_bones.new(n)
    eb.head, eb.tail = h, t
    d = (t - h).normalized()
    eb.align_roll(Vector((0, 0, 1)) if abs(d.z) < 0.8 else Vector((1, 0, 0)))
for n, (h, t, par) in BONES.items():
    if par:
        arm_d.edit_bones[n].parent = arm_d.edit_bones[par]
arm_d.edit_bones["RiderRoot"].use_deform = False
bpy.ops.object.mode_set(mode='OBJECT')
arm_d.display_type = 'STICK'

if not NOBAKE:
    dlib.smart_uv(rider, 60.0, 0.002)
    pr = dlib.bake_object(rider, "Rider", TEX)
    pr = dlib.pack_orm(pr, "Rider")
    MF = dlib.final_material("M_Rider", pr)
    rider.data.polygons.foreach_set("material_index", [0] * len(rider.data.polygons))
    rider.data.materials.clear()
    rider.data.materials.append(MF)
    for nm in ("hem", "shp"):
        a = rider.data.attributes.get(nm)
        if a:
            rider.data.attributes.remove(a)

# thin cloak: solidify only cloak + aventail would need separation; give the whole sheet set 8 mm
bpy.ops.object.select_all(action='DESELECT')
rider.select_set(True)
bpy.context.view_layer.objects.active = rider
bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)
rider.parent = arm
md = rider.modifiers.new("RiderRig", 'ARMATURE')
md.object = arm
print("TRIANGLES rider:", dlib.tri_count(rider))


# ------------------------------------------------------------------ RiderIdle (90 frames, 3 s loop)
def idle(f, ph):
    p = {}
    br = math.sin(2 * ph)                       # two breaths per loop
    p["Spine02"] = [('y', 0.012 * br)]
    p["Chest"] = [('y', -0.018 * br), ('x', 0.01 * math.sin(ph))]
    p["Pelvis"] = [('x', 0.008 * math.sin(ph + 0.5))]
    p["Neck"] = [('z', 0.08 * math.sin(ph)), ('y', 0.02 * math.sin(2 * ph + 1.0))]
    p["Head"] = [('z', 0.14 * math.sin(ph - 0.35)), ('y', -0.03 * math.sin(2 * ph))]
    p["Beard"] = [('x', 0.06 * math.sin(3 * ph - 0.6)), ('y', 0.05 * math.sin(2 * ph - 1.2))]
    for sfx, s in (("_L", 1), ("_R", -1)):
        p["Clavicle" + sfx] = [('y', 0.02 * br)]
        p["UpperArm" + sfx] = [('y', -0.03 * br)]
        p["Forearm" + sfx] = [('y', 0.035 * br)]
        p["Hand" + sfx] = [('y', -0.02 * br)]
    for i in range(1, CAPE_N + 1):
        amp = 0.06 + 0.05 * i
        p[f"Cape{i:02d}"] = [('y', -amp * math.sin(4 * ph - 1.1 * i) - 0.02 * math.sin(ph)),
                             ('z', 0.05 * i * math.sin(2 * ph - 0.7 * i)),
                             ('x', 0.03 * i * math.sin(3 * ph - 0.9 * i))]
    return p


dlib.write_action(arm, "RiderIdle", 90, idle, loop=True, paired=())
arm.animation_data.action = bpy.data.actions["RiderIdle"]
sc.frame_start, sc.frame_end = 0, 90
out = os.path.join(dlib.OUT_DIR, "Rider.blend")
bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
print(f"saved {out} total {time.time() - T0:.1f}s")
