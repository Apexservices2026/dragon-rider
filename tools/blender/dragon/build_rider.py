"""Build the Viking dragon rider procedurally (Blender 5.0, headless).

Run (after build_dragon.py):
  blender -b --factory-startup --python-exit-code 1 -P tools/blender/dragon/build_rider.py -- [--nobake] [--size 4096]

Seated Viking warrior (~1.85 m standing): sculpted head (brow ridge, nose, cheekbones, deep
eye sockets) under a Gjermundbu-style spectacle helmet with mail aventail; full beard with two
iron-ringed braids; thick wolf-fur mantle over a mail byrnie; mail sleeves, wool forearms with
laced leather bracers; gloved fists wrapped round the saddle horn; wool trousers with spiral
leg-wraps (winingas) and turned-cuff boots; broad belt with buckle, two pouches and a seax;
bearded axe at the right hip; round painted shield on the back; heavy folded wool cloak.

Chainmail uses a surface-aligned ring lattice (per-vertex 'mailuv' parameterisation, rings
~1.2 cm, staggered rows) instead of a 3D lattice, so it cannot produce slicing moire.
The dragon (Dragon.blend) is loaded only as a fitting reference (ray casts for the legs,
cloak floor and the saddle-horn post). Rider origin = the dragon's Saddle seat point.
Output: Saved/Generated/Dragon/Rider.blend (+ baked T_Rider_* textures).
"""
import sys
import os
import math
import time
import bpy
import numpy as np
from mathutils import Vector

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
dv = np.array([v.co[:] for v in drag.data.vertices])
m = (dv[:, 0] > SEAT.x + 0.3) & (dv[:, 0] < SEAT.x + 0.8) & (np.abs(dv[:, 1]) < 0.12)
knob = dv[m][np.argmax(dv[m][:, 2])]
# horn post centre + radius at grip heights
POST = {}
for dz in (0.06, 0.10, 0.145):
    zz = knob[2] - dz
    sl = dv[m & (np.abs(dv[:, 2] - zz) < 0.012)]
    sl = sl[np.linalg.norm(sl[:, :2] - knob[:2], axis=1) < 0.12]
    c = sl[:, :2].mean(0)
    r = float(np.percentile(np.linalg.norm(sl[:, :2] - c, axis=1), 90))
    POST[dz] = (np.array((c[0], c[1], zz)) - np.array(SEAT), r)
print("seat", tuple(SEAT), "post", {k: (tuple(np.round(v[0], 3)), round(v[1], 3)) for k, v in POST.items()})


def flank_y(x, z, side):
    o = Vector((x, side * 1.6, z)) + SEAT
    hit, loc, nrm, idx = drag.ray_cast(o, Vector((0, -side, 0)))
    return abs(loc.y) if hit else 0.0


def top_z(x, y):
    o = Vector((x, y, 4.0)) + SEAT
    hit, loc, nrm, idx = drag.ray_cast(o, Vector((0, 0, -1)))
    return (loc.z - SEAT.z) if hit else -1.0


LEG_SAMPLES = {}
for side in (1, -1):
    for (x, z) in [(0.30, -0.02), (0.26, -0.20), (0.18, -0.40), (0.25, -0.48), (0.36, -0.50)]:
        LEG_SAMPLES[(side, x, z)] = flank_y(x, z, side)
CX = np.linspace(-1.6, 0.3, 40)
CY = np.linspace(-0.7, 0.7, 15)
CAPE_TOP = np.array([[top_z(float(x), float(y)) for y in CY] for x in CX])
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 30


def cape_floor(x, y):
    return CAPE_TOP[np.argmin(np.abs(CX - x)), np.argmin(np.abs(CY - y))]


# ------------------------------------------------------------------ materials
def m_skin(nb):
    co = nb.coord().outputs['Object']
    pores = nb.noise(co, 140.0, 3.0).outputs['Factor']
    n1 = nb.noise(co, 40.0, 5.0).outputs['Factor']
    n2 = nb.noise(co, 6.0, 3.0).outputs['Factor']
    col = nb.mix(nb.maprange(n2, 0.3, 0.7), (0.20, 0.095, 0.055), (0.30, 0.15, 0.09))
    col = nb.mix(nb.math('MULTIPLY', n1, 0.35), col, (0.30, 0.09, 0.06))      # weathered ruddy
    cav = nb.attr("cav").outputs['Factor']
    col = nb.mix(nb.math('MINIMUM', nb.math('MULTIPLY', cav, 1.3), 0.95), col, (0.012, 0.005, 0.003))   # eyes in shadow
    h = nb.math('ADD', nb.math('MULTIPLY', pores, 0.4), nb.math('MULTIPLY', n1, 0.6))
    return dict(color=col, rough=nb.math('ADD', 0.42, nb.math('MULTIPLY', n1, 0.2)),
                normal=nb.bump(h, 0.35, 0.003))


def m_hair(nb):
    co = nb.coord().outputs['Object']
    warp = nb.noise(co, 20.0, 2.0).outputs['Color']
    wco = nb.vadd(co, nb.vscale(warp, 0.01))
    strands = nb.noise(nb.vscale(wco, (220, 220, 9)), 3.0, 4.0, 0.6).outputs['Factor']
    locks = nb.noise(nb.vscale(wco, (45, 45, 3)), 3.0, 3.0).outputs['Factor']
    n2 = nb.noise(co, 8.0, 2.0).outputs['Factor']
    h = nb.math('ADD', nb.math('MULTIPLY', strands, 0.6), nb.math('MULTIPLY', locks, 0.5))
    col = nb.ramp(h, [(0.15, (0.012, 0.004, 0.002)), (0.45, (0.09, 0.028, 0.009)),
                      (0.7, (0.26, 0.085, 0.025)), (0.95, (0.50, 0.24, 0.09))])
    col = nb.mix(nb.math('MULTIPLY', nb.maprange(n2, 0.5, 0.8), 0.35), col, (0.30, 0.26, 0.22))
    return dict(color=col, rough=nb.mixf(strands, 0.7, 0.4), normal=nb.bump(h, 1.2, 0.006))


def m_mail(nb):
    """Surface-aligned staggered ring lattice from the 'mailuv' attribute (metres)."""
    uv = nb.attr("mailuv").outputs['Vector']
    u, v, _w = nb.sep(uv)
    S = 85.0                                      # rings per metre (~1.2 cm)
    vs = nb.math('MULTIPLY', v, S * 1.15)
    row = nb.math('FLOOR', vs)
    shift = nb.math('MULTIPLY', nb.math('MODULO', row, 2.0), 0.5)
    us = nb.math('ADD', nb.math('MULTIPLY', u, S), shift)
    fu = nb.math('SUBTRACT', nb.math('FRACT', us), 0.5)
    fv = nb.math('SUBTRACT', nb.math('FRACT', vs), 0.5)
    d = nb.math('SQRT', nb.math('ADD', nb.math('MULTIPLY', fu, fu), nb.math('MULTIPLY', fv, fv)))
    ring = nb.math('MULTIPLY', nb.maprange(d, 0.20, 0.30, 0.0, 1.0, 'SMOOTHSTEP'),
                   nb.maprange(d, 0.40, 0.50, 1.0, 0.0, 'SMOOTHSTEP'))
    co = nb.coord().outputs['Object']
    rust = nb.noise(co, 5.0, 4.0).outputs['Factor']
    dirt = nb.noise(co, 14.0, 3.0).outputs['Factor']
    # low albedo contrast (the rings live mostly in the normal + roughness maps)
    col = nb.mix(ring, (0.035, 0.034, 0.033), (0.14, 0.135, 0.13))
    col = nb.mix(nb.math('MULTIPLY', nb.maprange(rust, 0.55, 0.75), 0.6), col, (0.12, 0.055, 0.025))
    col = nb.mix(nb.math('MULTIPLY', dirt, 0.3), col, (0.03, 0.025, 0.02))
    return dict(color=col, rough=nb.mixf(ring, 0.65, 0.38), metal=nb.mixf(ring, 0.5, 0.95),
                normal=nb.bump(ring, 0.8, 0.004))


def m_wool(nb):
    co = nb.coord().outputs['Object']
    weave = nb.new("ShaderNodeTexWave", wave_type='BANDS', bands_direction='DIAGONAL')
    nb._in(weave.inputs['Vector'], co)
    weave.inputs['Scale'].default_value = 160.0
    folds = nb.noise(nb.vscale(co, (3, 3, 14)), 3.0, 3.0).outputs['Factor']
    n1 = nb.noise(co, 12.0, 4.0).outputs['Factor']
    col = nb.mix(nb.maprange(n1, 0.3, 0.7), (0.045, 0.035, 0.025), (0.09, 0.07, 0.05))
    col = nb.mix(nb.math('MULTIPLY', weave.outputs['Factor'], 0.3), col, (0.025, 0.02, 0.015))
    col = nb.mix(nb.math('MULTIPLY', nb.maprange(folds, 0.55, 0.75), 0.5), col, (0.02, 0.015, 0.01))
    h = nb.math('ADD', nb.math('MULTIPLY', weave.outputs['Factor'], 0.2), nb.math('MULTIPLY', folds, 1.0))
    return dict(color=col, rough=0.9, normal=nb.bump(h, 0.6, 0.01))


def m_cloak(nb):
    co = nb.coord().outputs['Object']
    weave = nb.new("ShaderNodeTexWave", wave_type='BANDS', bands_direction='DIAGONAL')
    nb._in(weave.inputs['Vector'], co)
    weave.inputs['Scale'].default_value = 110.0
    n1 = nb.noise(co, 6.0, 4.0).outputs['Factor']
    wear = nb.noise(co, 20.0, 5.0).outputs['Factor']
    edge = nb.attr("hem").outputs['Factor']
    col = nb.mix(nb.maprange(n1, 0.3, 0.7), (0.06, 0.007, 0.005), (0.12, 0.016, 0.010))
    col = nb.mix(nb.math('MULTIPLY', weave.outputs['Factor'], 0.25), col, (0.025, 0.004, 0.003))
    col = nb.mix(nb.math('MULTIPLY', nb.maprange(wear, 0.6, 0.8), 0.4), col, (0.08, 0.05, 0.035))
    hem = nb.math('MULTIPLY', nb.maprange(edge, 0.955, 0.97), nb.maprange(edge, 0.99, 0.98))
    col = nb.mix(hem, col, (0.20, 0.12, 0.03))
    return dict(color=col, rough=0.92, normal=nb.bump(weave.outputs['Factor'], 0.25, 0.002))


def m_leather(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 30.0, 6.0, 0.6).outputs['Factor']
    n2 = nb.noise(co, 5.0, 3.0).outputs['Factor']
    scuff = nb.noise(co, 60.0, 3.0).outputs['Factor']
    col = nb.mix(nb.maprange(n2, 0.3, 0.7), (0.05, 0.025, 0.012), (0.14, 0.075, 0.035))
    col = nb.mix(nb.math('MULTIPLY', nb.maprange(scuff, 0.6, 0.75), 0.5), col, (0.22, 0.14, 0.08))
    return dict(color=col, rough=nb.math('ADD', 0.42, nb.math('MULTIPLY', n1, 0.3)),
                normal=nb.bump(nb.math('ADD', n1, nb.math('MULTIPLY', scuff, 0.3)), 0.45, 0.004))


def m_fur(nb):
    co = nb.coord().outputs['Object']
    warp = nb.noise(co, 9.0, 2.0).outputs['Color']
    wco = nb.vadd(co, nb.vscale(warp, 0.03))
    strands = nb.noise(nb.vscale(wco, (160, 160, 22)), 3.0, 4.0, 0.6).outputs['Factor']
    tufts = nb.noise(nb.vscale(wco, (30, 30, 8)), 3.0, 3.0, 0.5).outputs['Factor']
    n2 = nb.noise(co, 4.0, 3.0).outputs['Factor']
    h = nb.math('ADD', nb.math('MULTIPLY', strands, 0.55), nb.math('MULTIPLY', tufts, 0.6))
    col = nb.ramp(h, [(0.15, (0.008, 0.005, 0.003)), (0.45, (0.07, 0.042, 0.022)),
                      (0.72, (0.22, 0.15, 0.085)), (0.95, (0.45, 0.38, 0.28))])
    col = nb.mix(nb.math('MULTIPLY', n2, 0.45), col, (0.09, 0.06, 0.035))
    return dict(color=col, rough=0.95, normal=nb.bump(h, 1.2, 0.01))


def m_iron(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 25.0, 5.0).outputs['Factor']
    n2 = nb.noise(co, 3.0, 3.0).outputs['Factor']
    pits = nb.noise(co, 180.0, 2.0).outputs['Factor']
    col = nb.mix(nb.maprange(n2, 0.45, 0.75), (0.20, 0.19, 0.18), (0.09, 0.055, 0.03))
    col = nb.mix(nb.math('MULTIPLY', n1, 0.3), col, (0.04, 0.04, 0.04))
    return dict(color=col, rough=nb.math('ADD', 0.28, nb.math('MULTIPLY', n1, 0.35)), metal=0.95,
                normal=nb.bump(nb.math('ADD', n1, nb.math('MULTIPLY', pits, 0.4)), 0.35, 0.003))


def m_wood(nb):
    co = nb.coord().outputs['Object']
    shp = nb.attr("shp").outputs['Vector']
    r, ang, face = nb.sep(shp)
    grain = nb.noise(nb.vscale(co, (4, 4, 60)), 3.0, 6.0, 0.6, 2.0).outputs['Factor']
    wood = nb.mix(nb.maprange(grain, 0.3, 0.7), (0.09, 0.045, 0.018), (0.24, 0.13, 0.055))
    seg = nb.math('MODULO', nb.math('FLOOR', nb.math('MULTIPLY', nb.math('ADD', ang, 3.14159), 8 / 6.28318)), 2.0)
    paint = nb.mix(seg, (0.36, 0.30, 0.18), (0.20, 0.012, 0.008))
    band = nb.math('MULTIPLY', nb.maprange(r, 0.42, 0.46), nb.maprange(r, 0.58, 0.54))
    paint = nb.mix(band, paint, (0.02, 0.02, 0.02))
    wear = nb.maprange(nb.noise(co, 9.0, 5.0).outputs['Factor'], 0.55, 0.7)
    paint = nb.mix(wear, paint, wood)
    col = nb.mix(face, wood, paint)
    return dict(color=col, rough=0.7, normal=nb.bump(grain, 0.4, 0.003))


def m_wrap(nb):
    """Spiral wool leg-wraps: attribute 'wrapuv' = (length along leg m, theta, 0)."""
    w = nb.attr("wrapuv").outputs['Vector']
    L, th, _z = nb.sep(w)
    band = nb.math('FRACT', nb.math('SUBTRACT', nb.math('MULTIPLY', L, 16.0), nb.math('MULTIPLY', th, 0.159)))
    edge = nb.math('MINIMUM', band, nb.math('SUBTRACT', 1.0, band))
    groove = nb.maprange(edge, 0.0, 0.08, 1.0, 0.0, 'SMOOTHSTEP')
    co = nb.coord().outputs['Object']
    weave = nb.noise(nb.vscale(co, (200, 200, 200)), 2.0, 2.0).outputs['Factor']
    n1 = nb.noise(co, 9.0, 3.0).outputs['Factor']
    col = nb.mix(nb.maprange(n1, 0.3, 0.7), (0.13, 0.11, 0.08), (0.22, 0.19, 0.14))
    col = nb.mix(groove, col, (0.03, 0.025, 0.02))
    h = nb.math('ADD', nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, groove), 1.0), nb.math('MULTIPLY', weave, 0.2))
    return dict(color=col, rough=0.92, normal=nb.bump(h, 0.8, 0.006))


def m_eye(nb):
    return dict(color=(0.05, 0.06, 0.07), rough=0.08)


MATS = [dlib.pbr_material("SRC_R_" + n, f) for n, f in
        [("Skin", m_skin), ("Hair", m_hair), ("Mail", m_mail), ("Wool", m_wool), ("Cloak", m_cloak),
         ("Leather", m_leather), ("Fur", m_fur), ("Iron", m_iron), ("Wood", m_wood), ("Wrap", m_wrap),
         ("Eye", m_eye)]]
SKIN, HAIR, MAIL, WOOL, CLOAK, LEATH, FUR, IRON, WOOD, WRAP, EYE = range(11)

A = Acc(vec=("shp", "mailuv", "wrapuv"))
BONES = {}
SHEET_VERTS = []      # (start, end) vertex ranges of single-sided sheets to solidify


def bone(n, h, t, par):
    BONES[n] = (Vector(tuple(h)), Vector(tuple(t)), par)


def V(*a):
    return np.array(a, float)


def mailuv(t, th, L, ra, rb):
    return (th * 0.5 * (ra + rb), L, 0.0)


def wrapuv(t, th, L, ra, rb):
    return (L, th, 0.0)


# ------------------------------------------------------------------ skeleton (local, origin = seat)
lean = math.radians(18)


def spine_pt(h):
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
HS = [0.0, 0.14, 0.30, 0.44, 0.60, 0.68]


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
    return a + dn * math.cos(ang) * l1 + pv * math.sin(ang) * l1, a + dn * dist


def chain_fill(info, nr, ns, joints_idx, names, caps=(True, True), pre=None, blend=0.3):
    """Assign joint-blended weights to the last loft (nr x ns verts + caps)."""
    J = [info['ctrlL'][k] for k in joints_idx]
    st = A.n - (nr * ns + int(caps[0]) + int(caps[1]))
    for i in range(nr):
        w = chain_weights(info['L'][i], J, names, blend=blend)
        if pre:
            w = pre(info['L'][i], w)
        for j in range(ns):
            A.W[st + i * ns + j] = w
    k = st + nr * ns
    if caps[0]:
        A.W[k] = {names[0]: 1.0}
        k += 1
    if caps[1]:
        A.W[k] = {names[-1]: 1.0}


# ------------------------------------------------------------------ torso (mail byrnie), skirt
torso_rows = []
for h, w, d in [(-0.06, 0.165, 0.135), (0.0, 0.19, 0.145), (0.12, 0.18, 0.135), (0.28, 0.205, 0.15),
                (0.42, 0.25, 0.165), (0.52, 0.262, 0.148), (0.58, 0.17, 0.105), (0.63, 0.07, 0.07)]:
    p = spine_pt(h)
    torso_rows.append((p[0], 0, p[2], w, d))
NRt, NSt = 44, 36
info = loft(A, torso_rows, NRt, NSt, up=(1, 0, 0), mat=MAIL, vattrs={"mailuv": mailuv},
            section=lambda t, th, L: 1.0 + 0.03 * math.exp(-((t - 0.62) / 0.08) ** 2) * max(0.0, math.cos(th)) ** 2)
J = [info['L'][0] + (h + 0.06) for h in HS]
st = A.n - (NRt * NSt + 2)
for i in range(NRt):
    w = chain_weights(info['L'][i], J, SP_CHAIN, blend=0.4)
    for j in range(NSt):
        A.W[st + i * NSt + j] = w
A.W[st + NRt * NSt] = {"Pelvis": 1.0}
A.W[st + NRt * NSt + 1] = {"Neck": 1.0}
# mail skirt, flared, with a hem ripple
sk_rows = [tuple(spine_pt(0.12)[[0, 1, 2]]) + (0.185, 0.14), (0.03, 0, 0.06, 0.225, 0.175), (0.04, 0, -0.05, 0.26, 0.20)]
sk_rows[0] = (spine_pt(0.12)[0], 0, spine_pt(0.12)[2], 0.185, 0.14)
loft(A, sk_rows, 14, 40, up=(1, 0, 0), cap0=False, cap1=False, mat=MAIL, vattrs={"mailuv": mailuv},
     section=lambda t, th, L: 1.0 + 0.04 * t * math.sin(8 * th),
     weight_fn=lambda t, L: wmix((1 - t, {"Spine01": 1.0}), (t, {"Pelvis": 1.0})))
SHEET_VERTS.append((A.n - 14 * 40, A.n))

# ------------------------------------------------------------------ belt: band, buckle, pouches, seax
bp = spine_pt(0.13)
belt = [(bp[0] + 0.15 * math.cos(a) * 1.03, 0.19 * math.sin(a) * 1.03, bp[2]) for a in np.linspace(0, 2 * math.pi, 49)]
belt_rows = [tuple(p) + (0.013, 0.042) for p in belt]
loft(A, belt_rows, 96, 8, up=(0, 0, 1), cap0=False, cap1=False, mat=LEATH,
     weight_fn=lambda t, L: {"Spine01": 0.5, "Pelvis": 0.5})
bf = V(bp[0] + 0.16, 0, bp[2])
for dy, dz, w_, h_ in ((0.0, 0.0, 0.006, 0.05),):
    pass
# buckle: rectangular iron frame (4 bars) + tongue
for (a, b) in [((0, -0.032, -0.03), (0, 0.032, -0.03)), ((0, -0.032, 0.03), (0, 0.032, 0.03)),
               ((0, -0.032, -0.03), (0, -0.032, 0.03)), ((0, 0.032, -0.03), (0, 0.032, 0.03)),
               ((0.002, -0.005, 0.0), (0.004, 0.03, 0.0))]:
    pa, pb = bf + V(*a), bf + V(*b)
    loft(A, [tuple(pa) + (0.006, 0.006), tuple(pb) + (0.006, 0.006)], 3, 8, up=(1, 0, 0), mat=IRON,
         weight_fn=lambda t, L: {"Spine01": 0.5, "Pelvis": 0.5})
loft(A, [tuple(bf + V(0.0, -0.11, 0.0)) + (0.009, 0.036), tuple(bf + V(0.0, -0.04, 0.0)) + (0.009, 0.036)], 3, 8,
     up=(0, 0, 1), mat=LEATH, weight_fn=lambda t, L: {"Spine01": 0.5, "Pelvis": 0.5})
# pouches (left hip front, back)
for a0 in (math.radians(55), math.radians(150)):
    pc = V(bp[0] + 0.165 * math.cos(a0), 0.205 * math.sin(a0), bp[2] - 0.05)
    out = V(math.cos(a0), math.sin(a0), 0) * 0.02
    loft(A, [tuple(pc + V(0, 0, 0.045)) + (0.05, 0.02), tuple(pc + out + V(0, 0, 0.01)) + (0.06, 0.035),
             tuple(pc + out * 0.8 + V(0, 0, -0.04)) + (0.05, 0.03), tuple(pc + V(0, 0, -0.06)) + (0.005, 0.005)],
         14, 16, up=tuple(V(math.cos(a0), math.sin(a0), 0)), mat=LEATH,
         weight_fn=lambda t, L: {"Pelvis": 1.0})
    loft(A, [tuple(pc + out * 1.6 + V(0, 0, 0.045)) + (0.052, 0.008), tuple(pc + out * 1.9 + V(0, 0, 0.005)) + (0.05, 0.006)],
         4, 10, up=tuple(V(math.cos(a0), math.sin(a0), 0)), mat=LEATH, weight_fn=lambda t, L: {"Pelvis": 1.0})
# seax across the front of the belt (sheath + antler grip)
s0 = V(bp[0] + 0.175, 0.13, bp[2] - 0.02)
s1 = V(bp[0] + 0.19, -0.10, bp[2] - 0.05)
loft(A, [tuple(s0) + (0.012, 0.03), tuple((s0 + s1) / 2) + (0.011, 0.028), tuple(s1) + (0.004, 0.012)], 12, 10,
     up=(1, 0, 0), mat=LEATH, weight_fn=lambda t, L: {"Pelvis": 1.0})
g1 = s0 + (s0 - s1) / np.linalg.norm(s0 - s1) * 0.10
loft(A, [tuple(s0) + (0.012, 0.014), tuple(g1) + (0.011, 0.013), tuple(g1 + (g1 - s0) * 0.15) + (0.004, 0.004)], 8, 10,
     up=(1, 0, 0), mat=WOOD, weight_fn=lambda t, L: {"Pelvis": 1.0})

# ------------------------------------------------------------------ neck + sculpted head
hc = spine_pt(0.78)
loft(A, [tuple(spine_pt(0.58)) + (0.07, 0.07), tuple(spine_pt(0.66)) + (0.062, 0.065), tuple(hc + V(0.01, 0, -0.10)) + (0.058, 0.062)],
     10, 24, up=(1, 0, 0), cap0=False, cap1=False, mat=SKIN,
     weight_fn=lambda t, L: wmix((1 - t, {"Neck": 1.0}), (t, {"Head": 1.0})))
HZ = np.array([-0.135, -0.11, -0.075, -0.04, 0.0, 0.04, 0.075, 0.105, 0.13, 0.148])
HW = np.array([0.040, 0.060, 0.074, 0.081, 0.086, 0.089, 0.087, 0.078, 0.058, 0.012])
HD = np.array([0.048, 0.072, 0.088, 0.098, 0.104, 0.108, 0.106, 0.096, 0.072, 0.014])
HX = np.array([0.032, 0.022, 0.013, 0.006, 0.0, -0.003, -0.005, -0.006, -0.006, -0.006])
FEAT = [  # z, |theta|, sz, sth, amp (relative radius)
    (-0.036, 0.0, 0.017, 0.10, 0.38), (0.012, 0.0, 0.03, 0.075, 0.22),    # nose tip, bridge
    (-0.040, 0.17, 0.012, 0.07, 0.08),                                    # nostril wings
    (0.034, 0.30, 0.013, 0.30, 0.15),                                     # brow ridge
    (0.012, 0.34, 0.014, 0.14, -0.16),                                    # eye sockets
    (-0.012, 0.72, 0.022, 0.25, 0.10),                                    # cheekbones
    (-0.055, 0.78, 0.02, 0.25, -0.035),                                   # cheek hollows
    (-0.072, 0.0, 0.010, 0.25, 0.035),                                    # lips
    (-0.112, 0.0, 0.020, 0.35, 0.12),                                     # chin
    (-0.090, 1.25, 0.020, 0.30, 0.05),                                    # jaw angle
    (0.00, 1.57, 0.03, 0.12, 0.06),                                       # ears (under aventail)
]


def head_pt(z, th, off=0.0):
    w = np.interp(z, HZ, HW)
    d = np.interp(z, HZ, HD)
    x0 = np.interp(z, HZ, HX)
    a = abs(math.atan2(math.sin(th), math.cos(th)))
    m = 1.0
    for (z0, t0, sz, st_, amp) in FEAT:
        m += amp * math.exp(-((z - z0) / sz) ** 2 - ((a - t0) / st_) ** 2)
    dx, dy = d * math.cos(th), w * math.sin(th)
    if math.cos(th) < 0:
        dx *= 1.05
    n = math.hypot(dx, dy) + 1e-9
    k = (n * m + off) / n
    return hc + V(x0 + dx * k, dy * k, z)


NZ, NTH = 46, 44
zs = np.concatenate([np.linspace(-0.135, 0.13, NZ - 1), [0.146]])
ths = np.linspace(-math.pi, math.pi, NTH, endpoint=False)
R = np.array([[head_pt(z, th) for th in ths] for z in zs])
CAV = np.array([[math.exp(-((z - 0.012) / 0.02) ** 2 - ((abs(th) - 0.34) / 0.2) ** 2) +
                 0.5 * math.exp(-((z + 0.045) / 0.012) ** 2 - ((abs(th) - 0.12) / 0.08) ** 2) for th in ths] for z in zs])
A.rings(R, closed=True, cap0=True, cap1=True, mat=SKIN, weights=[{"Head": 1.0}] * NZ, attrs={"cav": CAV.ravel()})
for sg in (1, -1):
    # eyes deep in the sockets
    ec = head_pt(0.012, sg * 0.34, -0.004)
    loft(A, [tuple(ec - V(0.011, 0, 0)) + (0.0005, 0.0005), tuple(ec) + (0.012, 0.012), tuple(ec + V(0.011, 0, 0)) + (0.0005, 0.0005)],
         8, 12, up=(0, 0, 1), mat=EYE, weight_fn=lambda t, L: {"Head": 1.0})
    # bushy brows
    b0, b1, b2 = head_pt(0.042, sg * 0.08, 0.004), head_pt(0.046, sg * 0.32, 0.006), head_pt(0.038, sg * 0.62, 0.003)
    loft(A, [tuple(b0) + (0.008, 0.007), tuple(b1) + (0.011, 0.009), tuple(b2) + (0.006, 0.005)], 12, 10, up=(1, 0, 0),
         mat=HAIR, weight_fn=lambda t, L: {"Head": 1.0},
         section=lambda t, th, L: 1.0 + 0.25 * abs(math.sin(L * 300 + th)))
    # moustache sweeping into the beard
    m0, m1 = head_pt(-0.052, sg * 0.05, 0.006), head_pt(-0.062, sg * 0.32, 0.01)
    m2 = head_pt(-0.10, sg * 0.42, 0.018)
    loft(A, [tuple(m0) + (0.010, 0.010), tuple(m1) + (0.014, 0.012), tuple(m2) + (0.01, 0.01)], 14, 12, up=(1, 0, 0),
         mat=HAIR, weight_fn=lambda t, L: {"Head": 1.0},
         section=lambda t, th, L: 1.0 + 0.2 * abs(math.sin(L * 250 + 2 * th)))

# beard shell over the lower face (closed slab: outer arc + inner arc per row)
rows = []
bz = np.linspace(-0.045, -0.136, 16)
for z in bz:
    g = sstep(-0.045, -0.13, z)
    tmax = 1.95
    outer = [head_pt(z, th, 0.008 + 0.036 * g + 0.008 * abs(math.sin(th * 13 + z * 260)) ** 2) for th in np.linspace(-tmax, tmax, 34)]
    inner = [head_pt(z, th, -0.004) for th in np.linspace(tmax, -tmax, 34)]
    rows.append(outer + inner)
A.rings(np.array(rows), closed=True, cap0=True, cap1=True, mat=HAIR, weights=[{"Head": 1.0}] * 16)
# hanging beard mass from the chin, splitting into two braids
chin = head_pt(-0.13, 0.0, 0.03)
bm_rows = [(chin[0] - 0.035, 0, chin[2] + 0.02, 0.085, 0.055), (chin[0] - 0.005, 0, chin[2] - 0.03, 0.08, 0.05),
           (chin[0] + 0.012, 0, chin[2] - 0.09, 0.062, 0.042), (chin[0] + 0.02, 0, chin[2] - 0.14, 0.045, 0.032),
           (chin[0] + 0.02, 0, chin[2] - 0.17, 0.035, 0.024)]
loft(A, bm_rows, 26, 28, up=(1, 0, 0), mat=HAIR, cap0=True, cap1=True,
     section=lambda t, th, L: 1.0 + 0.16 * abs(math.sin(9 * th + t * 14)) ** 2 + 0.06 * math.sin(23 * th + t * 30),
     weight_fn=lambda t, L: wmix((1 - t, {"Head": 1.0}), (t, {"Beard": 1.0})))
braid_top = V(chin[0] + 0.02, 0, chin[2] - 0.15)
for sg in (1, -1):
    b0 = braid_top + V(0, sg * 0.018, 0)
    rws = []
    for t in np.linspace(0, 1, 8):
        rws.append((b0[0] + 0.02 * t - 0.04 * t * t, b0[1] + sg * 0.008 * t, b0[2] - 0.30 * t,
                    0.021 * (1 - 0.5 * t), 0.019 * (1 - 0.5 * t)))
    loft(A, rws, 64, 16, up=(1, 0, 0), mat=HAIR, cap0=False, cap1=True,
         section=lambda t, th, L: 1.0 + 0.26 * abs(math.sin(1.5 * th + L * 100.0)),
         weight_fn=lambda t, L: {"Beard": 1.0})
    for tt in (0.55, 0.85):
        p = V(b0[0] + 0.02 * tt - 0.04 * tt * tt, b0[1] + sg * 0.008 * tt, b0[2] - 0.30 * tt)
        r = 0.021 * (1 - 0.5 * tt) + 0.004
        loft(A, [tuple(p + V(0, 0, 0.011)) + (r, r), tuple(p - V(0, 0, 0.011)) + (r, r)], 4, 12, up=(1, 0, 0),
             mat=IRON, weight_fn=lambda t, L: {"Beard": 1.0})
bone("Beard", tuple(chin + V(-0.02, 0, 0.0)), tuple(braid_top + V(-0.01, 0, -0.30)), "Head")

# ------------------------------------------------------------------ helmet (Gjermundbu-style, no horns)
hb = hc + V(0.0, 0, 0.048)
dome = [(hb[0] + 0.012, 0, hb[2] + dz, 0.103 * s, 0.12 * s) for dz, s in
        [(-0.008, 1.0), (0.04, 0.97), (0.08, 0.86), (0.115, 0.62), (0.135, 0.3), (0.142, 0.01)]]
loft(A, dome, 20, 32, up=(1, 0, 0), cap0=False, mat=IRON, weight_fn=lambda t, L: {"Head": 1.0})
band = [(hb[0] + 0.012 + 0.123 * math.cos(a), 0.106 * math.sin(a), hb[2] - 0.004) for a in np.linspace(0, 2 * math.pi, 49)]
loft(A, [tuple(p) + (0.008, 0.016) for p in band], 64, 8, up=(0, 0, 1), cap0=False, cap1=False, mat=IRON,
     weight_fn=lambda t, L: {"Head": 1.0})
for ang in (0.0, math.pi / 2):     # crest bands front-back and side-side
    cr = [(hb[0] + 0.012 + 0.121 * math.cos(a) * math.cos(ang), 0.105 * math.cos(a) * math.sin(ang), hb[2] + 0.142 * math.sin(a) + 0.002)
          for a in np.linspace(0.05, math.pi - 0.05, 17)]
    loft(A, [tuple(p) + (0.012, 0.006) for p in cr], 34, 8, up=(0, 0, 1), mat=IRON,
         weight_fn=lambda t, L: {"Head": 1.0})
# spectacle guard: two eye rings + nose guard, standing off the face
for sg in (1, -1):
    ec = head_pt(0.012, sg * 0.34, 0.012)
    ring = []
    for a in np.linspace(0, 2 * math.pi, 25):
        th_ = sg * 0.34 + 0.20 * math.cos(a)
        z_ = 0.012 + 0.024 * math.sin(a)
        ring.append(tuple(head_pt(z_, th_, 0.012 + 0.004 * max(0.0, math.cos(a)))))
    loft(A, [r + (0.006, 0.0075) for r in ring], 32, 8, up=(1, 0, 0), cap0=False, cap1=False, mat=IRON,
         weight_fn=lambda t, L: {"Head": 1.0})
    # cheek plate of the guard (down from the outer ring towards the cheekbone)
    loft(A, [tuple(head_pt(0.0, sg * 0.55, 0.014)) + (0.006, 0.007), tuple(head_pt(-0.035, sg * 0.70, 0.015)) + (0.005, 0.006)],
         6, 8, up=(1, 0, 0), mat=IRON, weight_fn=lambda t, L: {"Head": 1.0})
ng = [tuple(head_pt(z, 0.0, 0.012)) + (0.009, 0.006) for z in (0.06, 0.035, 0.01, -0.015, -0.03)]
loft(A, ng, 14, 8, up=(1, 0, 0), mat=IRON, weight_fn=lambda t, L: {"Head": 1.0})
# rivets on the band
for a in np.linspace(0, 2 * math.pi, 14, endpoint=False):
    p = V(hb[0] + 0.012 + 0.131 * math.cos(a), 0.114 * math.sin(a), hb[2] - 0.004)
    nrm = V(math.cos(a), math.sin(a), 0)
    loft(A, [tuple(p - nrm * 0.003) + (0.0055, 0.0055), tuple(p + nrm * 0.004) + (0.003, 0.003)], 3, 8,
         up=(0, 0, 1), mat=IRON, weight_fn=lambda t, L: {"Head": 1.0})
# mail aventail at the back and sides
NU, NVv = 34, 12
P = np.zeros((NVv, NU, 3))
muv = np.zeros((NVv, NU, 3))
for vi, v in enumerate(np.linspace(0, 1, NVv)):
    for ui, a in enumerate(np.linspace(math.radians(78), math.radians(282), NU)):
        rr = 1.0 + 0.38 * v
        P[vi, ui] = (hb[0] + 0.006 + 0.124 * rr * math.cos(a) - 0.035 * v, 0.108 * rr * math.sin(a), hb[2] - 0.15 * v)
        muv[vi, ui] = (a * 0.13, v * 0.15, 0)
A.grid(P, mat=MAIL, weights=[wmix((1 - v * 0.7, {"Head": 1.0}), (v * 0.7, {"Neck": 1.0})) for v in np.linspace(0, 1, NVv) for _ in range(NU)],
       attrs={"mailuv": muv.reshape(-1, 3)})
SHEET_VERTS.append((A.n - NU * NVv, A.n))

# ------------------------------------------------------------------ arms, bracers, gloved fists on the horn post
(pc_hi, r_hi), (pc_md, r_md), (pc_lo, r_lo) = POST[0.06], POST[0.10], POST[0.145]
for sg, sfx, (pcen, prad) in ((1, "_L", (pc_md, r_md)), (-1, "_R", (pc_lo, r_lo))):
    clav0 = spine_pt(0.53) + V(0.0, sg * 0.03, 0)
    sh = spine_pt(0.52) + V(-0.01, sg * 0.245, -0.025)
    rr = prad + 0.012
    palm = pcen + V(rr * math.cos(sg * 2.3), rr * math.sin(sg * 2.3), 0)       # behind/outside the post
    wr_t = palm + V(-0.07, sg * 0.035, 0.01)
    elbow, wr = two_bone(sh, wr_t, 0.31, 0.28, sh + V(-0.12, sg * 0.40, -0.25))
    bone("Clavicle" + sfx, clav0, sh, "Chest")
    bone("UpperArm" + sfx, sh, elbow, "Clavicle" + sfx)
    bone("Forearm" + sfx, elbow, wr, "UpperArm" + sfx)
    bone("Hand" + sfx, wr, palm, "Forearm" + sfx)
    ua = elbow - sh
    # upper arm (mail sleeve): deltoid, biceps, elbow
    rows = [tuple(clav0) + (0.062, 0.062), tuple(sh) + (0.072, 0.072), tuple(sh + ua * 0.3) + (0.060, 0.064),
            tuple(sh + ua * 0.6) + (0.054, 0.056), tuple(elbow) + (0.046, 0.046), tuple(elbow + (wr - elbow) * 0.12) + (0.045, 0.044)]
    info = loft(A, rows, 34, 20, up=(0, 0, 1), mat=MAIL, vattrs={"mailuv": mailuv},
                section=lambda t, th, L: 1.0 + 0.06 * math.exp(-((t - 0.45) / 0.15) ** 2) * max(0.0, math.cos(th)),
                cap1=False)
    J = [info['ctrlL'][k] for k in (0, 1, 4, 5)]
    st = A.n - (34 * 20 + 1)
    for i in range(34):
        w = chain_weights(info['L'][i], J, ["Chest", "UpperArm" + sfx, "Forearm" + sfx], blend=0.3)
        if info['L'][i] < J[1] + 0.05:
            w = wmix((0.6, w), (0.4, {"Clavicle" + sfx: 1.0}))
        for j in range(20):
            A.W[st + i * 20 + j] = w
    A.W[st + 34 * 20] = {"Chest": 1.0}
    # forearm (wool sleeve, muscular taper)
    fa = wr - elbow
    rows = [tuple(elbow - fa * 0.05) + (0.046, 0.044), tuple(elbow + fa * 0.25) + (0.050, 0.045),
            tuple(elbow + fa * 0.6) + (0.041, 0.035), tuple(wr) + (0.033, 0.027)]
    loft(A, rows, 26, 22, up=(0, 0, 1), mat=WOOL, cap0=False, cap1=True,
         weight_fn=lambda t, L, s=sfx: wmix((max(0.0, 1 - t * 6), {"UpperArm" + s: 1.0}), (min(1.0, t * 6), {"Forearm" + s: 1.0})))
    # laced leather bracer
    b0, b1 = elbow + fa * 0.30, wr + fa * 0.03
    loft(A, [tuple(b0) + (0.056, 0.051), tuple(b0 + (b1 - b0) * 0.5) + (0.050, 0.043), tuple(b1) + (0.042, 0.036)], 16, 22,
         up=(0, 0, 1), cap0=False, cap1=False, mat=LEATH, weight_fn=lambda t, L, s=sfx: {"Forearm" + s: 1.0},
         section=lambda t, th, L: 1.0 + 0.05 * max(0.0, math.cos(th)) ** 8 * abs(math.sin(L * 160)) + 0.03 * math.sin(t * math.pi))
    for rt in (0.33, 0.97):      # rolled edges
        p = elbow + fa * rt
        r0 = 0.057 if rt < 0.5 else 0.044
        loft(A, [tuple(p - fa * 0.01) + (r0, r0 * 0.92), tuple(p + fa * 0.01) + (r0, r0 * 0.92)], 3, 22, up=(0, 0, 1),
             cap0=False, cap1=False, mat=LEATH, weight_fn=lambda t, L, s=sfx: {"Forearm" + s: 1.0})
    # glove: back of hand / palm wrapped round the post
    hw = {"Hand" + sfx: 1.0}
    phi_palm = sg * 2.3
    pts = []
    for k, ph in enumerate(np.linspace(phi_palm + sg * 0.35, phi_palm - sg * 0.75, 5)):
        pts.append(tuple(pcen + V((rr + 0.012) * math.cos(ph), (rr + 0.012) * math.sin(ph), 0.0)) + (0.03, 0.042))
    loft(A, [tuple(wr) + (0.034, 0.028)] + pts, 22, 18, up=(0, 0, 1), mat=LEATH, weight_fn=lambda t, L: hw)
    # four fingers curling round the front of the post, knuckles proud
    for f in range(4):
        z_ = 0.027 - f * 0.018
        arc = np.linspace(phi_palm - sg * 0.55, phi_palm - sg * (3.6 - 0.12 * f), 6)
        fr = []
        for k, ph in enumerate(arc):
            rad = rr + (0.016 if k == 0 else 0.004)
            r_ = 0.0105 if k < 4 else 0.0085
            fr.append(tuple(pcen + V(rad * math.cos(ph), rad * math.sin(ph), z_)) + (r_, r_))
        loft(A, fr, 14, 10, up=(0, 0, 1), mat=LEATH, weight_fn=lambda t, L: hw)
    # thumb wrapping the other way over the index finger
    tarc = np.linspace(phi_palm + sg * 0.4, phi_palm + sg * 1.5, 4)
    tr = [tuple(pcen + V((rr + 0.006) * math.cos(ph), (rr + 0.006) * math.sin(ph), 0.04 - 0.008 * k)) + (0.012, 0.011)
          for k, ph in enumerate(tarc)]
    loft(A, tr, 10, 10, up=(0, 0, 1), mat=LEATH, weight_fn=lambda t, L: hw)

# ------------------------------------------------------------------ legs: trousers, leg-wraps, boots
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
    rows = [tuple(hip + V(0, -sg * 0.04, 0.02)) + (0.105, 0.105), tuple(mid_t) + (0.092, 0.096), tuple(knee) + (0.066, 0.068),
            tuple(s_shin) + (0.06, 0.062), tuple(ankle) + (0.048, 0.05)]
    info = loft(A, rows, 36, 22, up=(1, 0, 0), mat=WOOL,
                section=lambda t, th, L: 1.0 + 0.035 * math.sin(3 * th + L * 45) * (1 - t) + 0.03 * math.exp(-((t - 0.45) / 0.06) ** 2))
    J = [info['ctrlL'][k] for k in (0, 2, 4)]
    st = A.n - (36 * 22 + 2)
    for i in range(36):
        w = chain_weights(info['L'][i], J, ["Thigh" + sfx, "Shin" + sfx], blend=0.3)
        if info['L'][i] < 0.12:
            g = info['L'][i] / 0.12
            w = wmix((1 - g, {"Pelvis": 1.0}), (g, w))
        for j in range(22):
            A.W[st + i * 22 + j] = w
    A.W[st + 36 * 22] = {"Pelvis": 1.0}
    A.W[st + 36 * 22 + 1] = {"Shin" + sfx: 1.0}
    # spiral wool leg-wraps (winingas) knee -> ankle
    loft(A, [tuple(knee + (ankle - knee) * 0.12) + (0.066, 0.069), tuple(s_shin) + (0.064, 0.067),
             tuple(ankle + (knee - ankle) * 0.25) + (0.057, 0.06)], 20, 22, up=(1, 0, 0), cap0=False, cap1=False,
         mat=WRAP, weight_fn=lambda t, L, s=sfx: {"Shin" + s: 1.0}, vattrs={"wrapuv": wrapuv},
         section=lambda t, th, L: 1.0 + 0.03 * abs(math.sin(L * 50.3 - th * 0.5)))
    # garter strap with a small iron hook at the top of the wraps
    gp = knee + (ankle - knee) * 0.12
    loft(A, [tuple(gp - (ankle - knee) * 0.01) + (0.069, 0.072), tuple(gp + (ankle - knee) * 0.015) + (0.069, 0.072)], 3, 26,
         up=(1, 0, 0), cap0=False, cap1=False, mat=LEATH, weight_fn=lambda t, L, s=sfx: {"Shin" + s: 1.0})
    # boot: shaft with turned cuff, instep, toe, sole
    fd = toe - ankle
    loft(A, [tuple(ankle + (knee - ankle) * 0.30) + (0.064, 0.067), tuple(ankle + (knee - ankle) * 0.26) + (0.066, 0.069),
             tuple(ankle + (knee - ankle) * 0.22) + (0.058, 0.061), tuple(ankle + V(0, 0, 0.03)) + (0.054, 0.058),
             tuple(ankle) + (0.052, 0.062), tuple(ankle + fd * 0.55 + V(0, 0, -0.018)) + (0.047, 0.037),
             tuple(toe) + (0.038, 0.029), tuple(toe + fd * 0.09) + (0.012, 0.012)], 26, 18, up=(0, 0, 1), mat=LEATH,
         weight_fn=lambda t, L, s=sfx: {"Foot" + s: 1.0} if t > 0.55 else ({"Shin" + s: 1.0} if t < 0.35 else {"Shin" + s: 0.5, "Foot" + s: 0.5}),
         section=lambda t, th, L: 1.0 + 0.04 * math.sin(L * 90 + th) * (1 - t))
    loft(A, [tuple(ankle + V(-0.03, 0, -0.05)) + (0.042, 0.012), tuple(ankle + fd * 0.5 + V(0, 0, -0.05)) + (0.045, 0.012),
             tuple(toe + fd * 0.06 + V(0, 0, -0.022)) + (0.03, 0.01)], 12, 14, up=(0, 0, 1), mat=LEATH,
         weight_fn=lambda t, L, s=sfx: {"Foot" + s: 1.0})

# ------------------------------------------------------------------ thick wolf-fur mantle
mc = spine_pt(0.545) + V(-0.015, 0, 0)
ring = []
for a in np.linspace(-math.pi, math.pi, 41):
    rx = 0.175 if math.cos(a) > 0 else 0.21
    ring.append((mc[0] + rx * math.cos(a) * 0.95 - 0.01, 0.27 * math.sin(a), mc[2] - 0.03 * math.cos(a) + 0.025 * (1 - abs(math.sin(a)))))
ring.append(ring[1])
loft(A, [tuple(p) + (0.072, 0.082) for p in ring], 110, 20, up=(0, 0, 1), cap0=False, cap1=False, mat=FUR,
     section=lambda t, th, L: 1.0 + 0.30 * abs(math.sin(L * 95.0 + 5 * th)) ** 3 + 0.15 * abs(math.sin(L * 41.0 - 3 * th)) ** 2 + 0.05 * math.sin(L * 160 - 7 * th),
     weight_fn=lambda t, L: {"Chest": 0.85, "Neck": 0.15})
for sg, sfx in ((1, "_L"), (-1, "_R")):
    s0 = spine_pt(0.53) + V(-0.01, sg * 0.24, 0.0)
    loft(A, [tuple(s0 + V(-0.09, -sg * 0.04, 0.02)) + (0.07, 0.07), tuple(s0 + V(0.0, sg * 0.03, 0.045)) + (0.11, 0.085),
             tuple(s0 + V(0.07, sg * 0.05, -0.02)) + (0.06, 0.055)], 20, 22, up=(0, 0, 1), mat=FUR,
         section=lambda t, th, L: 1.0 + 0.18 * abs(math.sin(L * 50.0 + 4 * th)) + 0.06 * math.sin(L * 140 + 6 * th),
         weight_fn=lambda t, L, s=sfx: {"Chest": 0.6, "Clavicle" + s: 0.4})

# ------------------------------------------------------------------ heavy folded cloak (drops down the back, streams over the dragon)
NU, NVc = 36, 34
P = np.zeros((NVc, NU, 3))
Wt, hem = [], np.zeros((NVc, NU))
CAPE_N = 4
V_DROP = 0.36


def back_depth(h):
    return float(np.interp(h, [0.0, 0.12, 0.28, 0.42, 0.52, 0.58], [0.145, 0.135, 0.15, 0.165, 0.15, 0.105]))


for vi, v in enumerate(np.linspace(0, 1, NVc)):
    for ui, u in enumerate(np.linspace(-1, 1, NU)):
        a = u * math.radians(82)
        fold = math.sin(u * math.pi * 3.5 + 0.4) * (0.35 + 0.65 * v)        # vertical folds
        if v <= V_DROP:
            s_ = v / V_DROP
            h = 0.55 - 0.45 * s_
            pc = spine_pt(h)
            depth = back_depth(h) + 0.03 + 0.018 * fold * s_
            x = pc[0] - depth * math.cos(a)
            y = (0.225 + 0.035 * s_) * math.sin(a) * (1 + 0.04 * fold * s_)
            z = pc[2] + 0.02 * (1 - s_)
        else:
            s2 = (v - V_DROP) / (1 - V_DROP)
            pc = spine_pt(0.10)
            x = pc[0] - (back_depth(0.10) + 0.03) * math.cos(a) - 1.05 * s2 - 0.2 * s2 * s2
            y = 0.26 * math.sin(a) * (1 + 0.85 * s2)
            z = pc[2] - 0.20 * s2 + 0.045 * fold * (0.4 + s2)
            z += 0.025 * math.sin(u * 7 + s2 * 9) * s2
            fl = cape_floor(x, y)
            z = max(z, fl + 0.075 + 0.04 * (1 - abs(u)))
        P[vi, ui] = (x, y, z)
        cv = max(0.0, (v - 0.30) / 0.70)
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
SHEET_VERTS.append((A.n - NU * NVc, A.n))
cen = P[:, NU // 2]
for i in range(CAPE_N):
    a_ = cen[int((0.30 + 0.70 * i / CAPE_N) * (NVc - 1))]
    b_ = cen[int((0.30 + 0.70 * (i + 1) / CAPE_N) * (NVc - 1))]
    bone(f"Cape{i + 1:02d}", a_, b_, "Chest" if i == 0 else f"Cape{i:02d}")
# cloak pin (penannular brooch) at the right shoulder
br = spine_pt(0.56) + V(0.12, -0.17, 0.0)
ring_b = [tuple(br + V(0.0, 0.028 * math.cos(a), 0.028 * math.sin(a)) + V(0.012, 0, 0)) for a in np.linspace(0.3, 2 * math.pi - 0.3, 18)]
loft(A, [r + (0.005, 0.005) for r in ring_b], 30, 8, up=(1, 0, 0), mat=IRON, weight_fn=lambda t, L: {"Chest": 1.0})
loft(A, [tuple(br + V(0.016, -0.03, 0.03)) + (0.003, 0.003), tuple(br + V(0.016, 0.04, -0.04)) + (0.003, 0.003)], 4, 6,
     up=(1, 0, 0), mat=IRON, weight_fn=lambda t, L: {"Chest": 1.0})

# ------------------------------------------------------------------ round shield on the back
sh_c = spine_pt(0.36) + V(-0.245, 0, 0.0)
sh_n = V(-math.cos(math.radians(28)), 0, math.sin(math.radians(28)))
sh_u = np.cross(sh_n, V(0, 1, 0))
sh_u /= np.linalg.norm(sh_u)
sh_v = np.cross(sh_n, sh_u)
R_SH, NRr, NA = 0.40, 12, 48
verts, faces, shp = [], [], []
for side in (0, 1):
    off = sh_n * (0.012 if side == 0 else -0.012)
    for ri, r in enumerate(np.linspace(0.0, R_SH, NRr)):
        for ai, a in enumerate(np.linspace(0, 2 * math.pi, NA, endpoint=False)):
            dome_h = 0.015 * (1 - (r / R_SH) ** 2) if side == 0 else 0.0
            verts.append(sh_c + off + sh_n * dome_h + sh_u * r * math.cos(a) + sh_v * r * math.sin(a))
            shp.append((r / R_SH, math.atan2(math.sin(a), math.cos(a)), 1.0 if side == 0 else 0.0))
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
loft(A, [tuple(sh_c + sh_n * 0.02) + (0.078, 0.078), tuple(sh_c + sh_n * 0.06) + (0.062, 0.062),
         tuple(sh_c + sh_n * 0.085) + (0.03, 0.03), tuple(sh_c + sh_n * 0.09) + (0.002, 0.002)],
     12, 28, up=tuple(sh_u), cap0=True, cap1=False, mat=IRON, weight_fn=lambda t, L: {"Chest": 1.0})
rim = [tuple(sh_c + sh_u * R_SH * math.cos(a) + sh_v * R_SH * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 41)]
loft(A, [r + (0.014, 0.018) for r in rim], 80, 8, up=tuple(sh_n), cap0=False, cap1=False, mat=LEATH,
     weight_fn=lambda t, L: {"Chest": 1.0})
# baldric across the chest
loft(A, [tuple(spine_pt(0.52) + V(0.10, 0.17, 0.02)) + (0.032, 0.008), tuple(spine_pt(0.36) + V(0.175, 0.0, 0.0)) + (0.032, 0.008),
         tuple(spine_pt(0.18) + V(0.15, -0.16, 0.0)) + (0.032, 0.008)], 22, 6, up=(1, 0, 0), cap0=False, cap1=False,
     mat=LEATH, weight_fn=lambda t, L: {"Chest": 1 - t * 0.6, "Spine01": t * 0.6})

# ------------------------------------------------------------------ bearded axe at the RIGHT hip (camera side), head up by the belt
ax_top = V(0.13, -0.245, 0.31)
ax_bot = V(-0.10, -0.31, -0.36)
hd = ax_bot - ax_top
hd /= np.linalg.norm(hd)
loft(A, [tuple(ax_top + hd * -0.06) + (0.017, 0.017), tuple(ax_top + hd * 0.3) + (0.018, 0.018), tuple(ax_bot) + (0.02, 0.02),
         tuple(ax_bot + hd * 0.02) + (0.012, 0.012)], 24, 12, up=(0, 1, 0), mat=WOOD, weight_fn=lambda t, L: {"Pelvis": 1.0})
for tt in (0.62, 0.70):       # leather grip wraps
    p = ax_top + hd * (0.67 * tt / 0.67)
    p = ax_top + (ax_bot - ax_top) * tt
    loft(A, [tuple(p) + (0.021, 0.021), tuple(p + hd * 0.05) + (0.021, 0.021)], 3, 12, up=(0, 1, 0), cap0=False, cap1=False,
         mat=LEATH, weight_fn=lambda t, L: {"Pelvis": 1.0})
blade_dir = np.cross(hd, V(0, 1, 0))
blade_dir /= np.linalg.norm(blade_dir)
if blade_dir[0] < 0:
    blade_dir = -blade_dir
prof = [(-0.035, 0.04), (0.04, 0.034), (0.12, 0.05), (0.2, 0.085), (0.225, 0.035), (0.22, -0.05),
        (0.19, -0.14), (0.145, -0.15), (0.12, -0.07), (0.065, -0.035), (-0.035, -0.04)]
up_haft = -hd
side_n = V(0, 1, 0)
verts = []
nP = len(prof)
for s in (1, -1):
    for a, b in prof:
        th = 0.02 * (1 - max(0.0, a) / 0.23) + 0.0015
        verts.append(ax_top + up_haft * (b - 0.02) + blade_dir * a + side_n * s * th)
faces = [list(range(nP)), list(range(2 * nP - 1, nP - 1, -1))]
for i in range(nP):
    j = (i + 1) % nP
    faces.append([i, j, nP + j, nP + i])
A.add(verts, faces, mat=IRON, weights={"Pelvis": 1.0})
# axe hangs from a belt frog loop
loft(A, [tuple(ax_top + hd * 0.08 + V(0, 0.022, 0)) + (0.012, 0.028), tuple(ax_top + hd * 0.08 + V(0, -0.025, 0)) + (0.012, 0.028)],
     3, 10, up=tuple(hd), mat=LEATH, weight_fn=lambda t, L: {"Pelvis": 1.0})

# ------------------------------------------------------------------ build + rig
sheet_mask = [0.0] * A.n
for a_, b_ in SHEET_VERTS:
    for i in range(a_, b_):
        sheet_mask[i] = 1.0
A.A["sheet"] = sheet_mask
rider = A.build("Rider", MATS)
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

# single-sided sheets (cloak, aventail, mail skirt) -> solidify so they render from both sides
bpy.ops.object.select_all(action='DESELECT')
rider.select_set(True)
bpy.context.view_layer.objects.active = rider
sv = np.zeros(len(rider.data.vertices))
rider.data.attributes["sheet"].data.foreach_get("value", sv)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
for p in rider.data.polygons:
    p.select = all(sv[i] > 0.5 for i in p.vertices)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.separate(type='SELECTED')
bpy.ops.object.mode_set(mode='OBJECT')
sheets = [o for o in bpy.context.selected_objects if o != rider][0]
so = sheets.modifiers.new("thick", 'SOLIDIFY')
so.thickness = 0.012
so.offset = 0.0
so.use_rim = True
so.use_even_offset = True
dlib.apply_modifiers(sheets)
bpy.ops.object.select_all(action='DESELECT')
sheets.select_set(True)
rider.select_set(True)
bpy.context.view_layer.objects.active = rider
bpy.ops.object.join()
if not NOBAKE:
    rider.data.polygons.foreach_set("material_index", [0] * len(rider.data.polygons))
    rider.data.materials.clear()
    rider.data.materials.append(MF)
    for nm in ("hem", "shp", "mailuv", "wrapuv", "sheet", "cav"):
        a = rider.data.attributes.get(nm)
        if a:
            rider.data.attributes.remove(a)

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
    br = math.sin(2 * ph)
    p["Spine02"] = [('y', 0.012 * br)]
    p["Chest"] = [('y', -0.018 * br), ('x', 0.01 * math.sin(ph))]
    p["Pelvis"] = [('x', 0.008 * math.sin(ph + 0.5))]
    p["Neck"] = [('z', 0.08 * math.sin(ph)), ('y', 0.02 * math.sin(2 * ph + 1.0))]
    p["Head"] = [('z', 0.14 * math.sin(ph - 0.35)), ('y', -0.03 * math.sin(2 * ph))]
    p["Beard"] = [('x', 0.06 * math.sin(3 * ph - 0.6)), ('y', 0.05 * math.sin(2 * ph - 1.2))]
    for sfx in ("_L", "_R"):
        p["Clavicle" + sfx] = [('y', 0.02 * br)]
        p["UpperArm" + sfx] = [('y', -0.03 * br)]
        p["Forearm" + sfx] = [('y', 0.035 * br)]
        p["Hand" + sfx] = [('y', -0.02 * br)]
    for i in range(1, CAPE_N + 1):
        amp = 0.05 + 0.045 * i
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
