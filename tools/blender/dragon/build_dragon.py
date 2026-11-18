"""Build the Dragon Rider dragon procedurally in Blender 5.0 (headless).

Run:  blender -b --factory-startup --python-exit-code 1 -P tools/blender/dragon/build_dragon.py -- [--nobake] [--size 4096]

Pipeline (all regenerable, output -> Game/DragonRider/Saved/Generated/Dragon/):
  1. geometry: lofted body/neck/head/tail, jaw, legs+toes+claws, horns, spines, teeth, eyes,
     saddle + girth strap, tail spade; wings = arm/finger bone tubes + cambered, scalloped
     membrane sheets. Every vertex is weighted to its bone at creation (parametric weights).
  2. procedural Cycles materials (scales, belly plates w/ ember seams, membrane veins,
     bone horns/claws, amber eyes, leather) baked to PNG: BaseColor, Normal (OpenGL +
     DirectX copy), ORM (AO/Roughness/Metallic), Emissive.
  3. DragonRig armature (+X forward, Z up, metres; origin = centre of mass) and actions
     Flap / Glide / DiveTuck / WingBeatStrong / Hover (30 fps).
  4. saves Dragon.blend (export.py writes FBX/GLB).
Blender: +X forward, +Y left, +Z up. 1 unit = 1 m.
"""
import sys
import os
import math
import time
import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlib  # noqa: E402
from dlib import Acc, loft, chain_weights, wmix, catmull, frames, sstep  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NOBAKE = "--nobake" in argv
BODY_TEX = int(argv[argv.index("--size") + 1]) if "--size" in argv else 4096
WING_TEX = BODY_TEX
T0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 30
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 1.0

# ============================================================================ body curve
# rows: x, y, z, half-width, half-height-up, half-height-down, dorsal ridge
BODY = np.array([
    (-6.05, 0, 0.26, 0.035, 0.03, 0.03, 0.000),
    (-5.60, 0, 0.16, 0.07, 0.06, 0.06, 0.010),
    (-4.95, 0, 0.02, 0.13, 0.11, 0.11, 0.020),
    (-4.20, 0, -0.07, 0.21, 0.18, 0.19, 0.030),
    (-3.45, 0, -0.06, 0.31, 0.27, 0.29, 0.040),
    (-2.80, 0, 0.00, 0.44, 0.38, 0.42, 0.050),
    (-2.25, 0, 0.06, 0.60, 0.52, 0.56, 0.050),
    (-1.50, 0, 0.08, 0.72, 0.62, 0.70, 0.050),
    (-0.40, 0, 0.02, 0.76, 0.64, 0.82, 0.045),
    (0.70, 0, 0.06, 0.82, 0.68, 0.86, 0.010),
    (1.50, 0, 0.24, 0.76, 0.66, 0.74, 0.030),
    (2.15, 0, 0.52, 0.55, 0.50, 0.52, 0.045),
    (2.75, 0, 0.92, 0.40, 0.38, 0.40, 0.045),
    (3.30, 0, 1.28, 0.32, 0.31, 0.33, 0.040),
    (3.85, 0, 1.52, 0.28, 0.27, 0.29, 0.035),
    (4.25, 0, 1.62, 0.34, 0.30, 0.27, 0.030),
    (4.60, 0, 1.62, 0.40, 0.30, 0.26, 0.030),
    (4.95, 0, 1.56, 0.32, 0.25, 0.20, 0.025),
    (5.30, 0, 1.46, 0.21, 0.17, 0.13, 0.020),
    (5.58, 0, 1.38, 0.13, 0.11, 0.09, 0.012),
    (5.72, 0, 1.33, 0.035, 0.03, 0.03, 0.000),
])
NR, NS = 320, 64
BS, BL = catmull(BODY, NR)
BC = BS[:, :3]
BT, BU, BSd = frames(BC, (0, 0, 1))
BX = BC[:, 0]


def x2L(x):
    return float(np.interp(x, BX, BL))


# radial bumps: x0, |theta0|, sigma_x, sigma_theta, amplitude (m)
BUMPS = [
    (1.25, 1.45, 0.45, 0.45, 0.07),   # shoulder muscle
    (-1.45, 1.55, 0.50, 0.50, 0.09),  # haunch
    (0.2, 1.75, 0.9, 0.35, 0.025),    # ribcage side
    (4.93, 0.78, 0.10, 0.22, 0.065),  # brow ridge
    (4.62, 1.45, 0.14, 0.30, 0.05),   # cheekbone
    (5.57, 0.55, 0.05, 0.22, 0.025),  # nostril
    (4.99, 1.12, 0.06, 0.16, -0.035), # eye socket
    (4.30, 0.65, 0.15, 0.40, 0.035),  # back of skull
    (5.20, 0.0, 0.25, 0.18, 0.015),   # snout ridge
    (2.6, 2.6, 0.5, 0.45, 0.03),      # throat
]


def section_pt(i_f, th, off=0.0):
    """Body surface point at fractional ring index i_f and angle th (0 = top, +pi/2 = left)."""
    i0 = int(np.clip(math.floor(i_f), 0, NR - 2))
    f = i_f - i0
    p = BS[i0] * (1 - f) + BS[i0 + 1] * f
    C = p[:3]
    w, hu, hd, ridge = p[3], p[4], p[5], p[6]
    T = BT[i0] * (1 - f) + BT[i0 + 1] * f
    U = BU[i0] * (1 - f) + BU[i0 + 1] * f
    S = np.cross(U, T)
    S /= np.linalg.norm(S)
    U /= np.linalg.norm(U)
    s, c = math.sin(th), math.cos(th)
    side = w * math.copysign(abs(s) ** (2 / 2.5), s)
    if c >= 0:
        up = hu * abs(c) ** (2 / 2.5)
    else:
        up = -hd * abs(c) ** (2 / 3.2)
    thw = abs(math.atan2(s, c))
    up += ridge * math.exp(-(thw / 0.16) ** 2)
    x = C[0]
    bump = 0.0
    for (x0, t0, sx, st, a) in BUMPS:
        bump += a * math.exp(-((x - x0) / sx) ** 2 - ((thw - t0) / st) ** 2)
    d = np.array([side, up])
    nd = np.linalg.norm(d) + 1e-9
    d2 = d / nd * (nd + bump + off)
    return C + d2[0] * S + d2[1] * U


def x2i(x):
    return float(np.interp(x, BX, np.arange(NR)))


def surf(x, th, off=0.0):
    return section_pt(x2i(x), th, off)


# ============================================================================ skeleton joints
TAIL_X = np.linspace(-6.05, -2.25, 11)
SPINE_X = [-2.25, -1.20, -0.10, 0.90, 2.15]
L_NECK0, L_HEAD0, L_END = x2L(2.15), x2L(4.25), BL[-1]
NECK_L = np.linspace(L_NECK0, L_HEAD0, 7)
CHAIN = [f"Tail{i:02d}" for i in range(10, 0, -1)] + [f"Spine{i:02d}" for i in range(1, 5)] + \
        [f"Neck{i:02d}" for i in range(1, 7)] + ["Head"]
CHAIN_J = [x2L(x) for x in TAIL_X] + [x2L(x) for x in SPINE_X[1:]] + list(NECK_L[1:]) + [L_END]
BLEND_OVR = {len(CHAIN_J) - 2: 0.10}   # tight neck/head joint


def body_w(L):
    return chain_weights(L, CHAIN_J, CHAIN, blend=0.4, blend_override=BLEND_OVR)


def Lpt(L):
    return np.array([np.interp(L, BL, BC[:, k]) for k in range(3)])


BONES = {}   # name -> (head, tail, parent)


def bone(name, h, t, parent):
    BONES[name] = (np.array(h, float), np.array(t, float), parent)


bone("Root", (0, 0, 0), (0, 0.6, 0), None)   # identity rest frame
bone("Body", (0, 0, 0), (0.6, 0, 0), "Root")
sp = [Lpt(x2L(x)) for x in SPINE_X]
for i in range(4):
    bone(f"Spine{i + 1:02d}", sp[i], sp[i + 1], "Body" if i == 0 else f"Spine{i:02d}")
tl = [Lpt(x2L(x)) for x in TAIL_X[::-1]]   # root -> tip
for i in range(10):
    bone(f"Tail{i + 1:02d}", tl[i], tl[i + 1], "Spine01" if i == 0 else f"Tail{i:02d}")
nk = [Lpt(L) for L in NECK_L]
for i in range(6):
    bone(f"Neck{i + 1:02d}", nk[i], nk[i + 1], "Spine04" if i == 0 else f"Neck{i:02d}")
bone("Head", nk[-1], Lpt(L_END), "Neck06")
JAW_H, JAW_T = np.array((4.42, 0, 1.47)), np.array((5.50, 0, 1.25))
bone("Jaw", JAW_H, JAW_T, "Head")

# ============================================================================ materials (procedural, baked later)
def m_scales(nb):
    co = nb.coord().outputs['Object']
    belly = nb.attr("belly").outputs['Factor']
    along = nb.attr("along").outputs['Factor']
    stretch = nb.vscale(co, (0.8, 1.0, 1.0))
    # warp for organic scale layout
    warp = nb.noise(co, 1.6, 2.0).outputs['Color']
    wco = nb.vadd(stretch, nb.vscale(warp, 0.03))
    vo = nb.voronoi(wco, 15.0, 'DISTANCE_TO_EDGE')
    vc = nb.voronoi(wco, 15.0, 'F1')
    edge = vo.outputs['Distance']
    groove = nb.maprange(edge, 0.0, 0.09, 1.0, 0.0, 'SMOOTHSTEP')       # 1 in gaps
    dome = nb.maprange(vc.outputs['Distance'], 0.0, 0.55, 1.0, 0.0, 'SMOOTHSTEP')
    big = nb.noise(co, 0.8, 3.0).outputs['Factor']
    fine = nb.noise(co, 60.0, 3.0).outputs['Factor']
    # belly plates: bands across the body along arc length
    band = nb.math('FRACT', nb.math('MULTIPLY', along, 4.2))
    pl_edge = nb.math('MINIMUM', band, nb.math('SUBTRACT', 1.0, band))
    plate_groove = nb.maprange(pl_edge, 0.0, 0.07, 1.0, 0.0, 'SMOOTHSTEP')
    bm = nb.maprange(belly, 0.25, 0.6, 0.0, 1.0, 'SMOOTHSTEP')
    # height
    h_sc = nb.math('ADD', nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, groove), 0.6),
                   nb.math('MULTIPLY', dome, 0.4))
    h_pl = nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, plate_groove), 0.9)
    h = nb.mixf(bm, h_sc, h_pl)
    h = nb.math('ADD', h, nb.math('MULTIPLY', fine, 0.12))
    nrm = nb.bump(h, 1.0, 0.012)
    nrm = nb.bump(nb.math('MULTIPLY', big, 1.0), 0.25, 0.05, nrm)
    # colour
    var = vc.outputs['Color']
    c_sc = nb.mix(0.18, (0.020, 0.019, 0.022), var, 'MULTIPLY')
    c_sc = nb.mix(nb.math('MULTIPLY', dome, 0.6), (0.011, 0.010, 0.012), (0.034, 0.032, 0.038))
    c_sc = nb.mix(nb.math('MULTIPLY', big, 0.5), c_sc, (0.05, 0.028, 0.022))
    c_sc = nb.mix(groove, c_sc, (0.004, 0.003, 0.003))
    c_pl = nb.mix(plate_groove, (0.11, 0.028, 0.012), (0.03, 0.006, 0.003))
    c_pl = nb.mix(nb.math('MULTIPLY', big, 0.6), c_pl, (0.06, 0.02, 0.012))
    col = nb.mix(bm, c_sc, c_pl)
    # ember glow: plate seams + soft underglow in low-flank scale gaps
    under = nb.maprange(belly, 0.05, 0.5, 0.0, 1.0, 'SMOOTHSTEP')
    glow = nb.math('ADD', nb.math('MULTIPLY', nb.math('MULTIPLY', bm, plate_groove), 0.9),
                   nb.math('MULTIPLY', nb.math('MULTIPLY', under, groove), 0.35))
    glow = nb.math('MULTIPLY', glow, nb.maprange(big, 0.3, 0.7, 0.5, 1.0))
    emit = nb.mix(glow, (0, 0, 0), (1.0, 0.22, 0.04))
    rough = nb.mixf(groove, nb.mixf(bm, 0.30, 0.45), 0.75)
    rough = nb.math('ADD', rough, nb.math('MULTIPLY', fine, 0.1))
    return dict(color=col, rough=rough, metal=0.0, normal=nrm, emit=emit)


def m_membrane(nb):
    co = nb.coord().outputs['Object']
    edge = nb.attr("edge").outputs['Factor']        # 1 near trailing edge
    warp = nb.noise(co, 0.9, 2.0).outputs['Color']
    wco = nb.vadd(co, nb.vscale(warp, 0.35))
    v1 = nb.voronoi(wco, 1.3, 'DISTANCE_TO_EDGE').outputs['Distance']
    v2 = nb.voronoi(nb.vscale(wco, 3.1), 1.0, 'DISTANCE_TO_EDGE').outputs['Distance']
    vein1 = nb.maprange(v1, 0.0, 0.035, 1.0, 0.0, 'SMOOTHSTEP')
    vein2 = nb.maprange(v2, 0.0, 0.03, 1.0, 0.0, 'SMOOTHSTEP')
    veins = nb.math('MAXIMUM', vein1, nb.math('MULTIPLY', vein2, 0.55))
    wr = nb.noise(nb.vscale(co, (1, 4, 1)), 9.0, 4.0, 0.6).outputs['Factor']
    fine = nb.noise(co, 45.0, 2.0).outputs['Factor']
    blot = nb.noise(co, 2.0, 3.0).outputs['Factor']
    h = nb.math('ADD', nb.math('MULTIPLY', veins, 0.8), nb.math('MULTIPLY', wr, 0.5))
    h = nb.math('ADD', h, nb.math('MULTIPLY', fine, 0.15))
    nrm = nb.bump(h, 0.7, 0.01)
    base = nb.mix(nb.maprange(blot, 0.35, 0.7), (0.022, 0.008, 0.008), (0.05, 0.012, 0.010))
    base = nb.mix(nb.math('MULTIPLY', edge, 0.8), base, (0.12, 0.022, 0.010))
    col = nb.mix(nb.math('MULTIPLY', veins, 0.8), base, (0.11, 0.02, 0.01))
    thin = nb.math('ADD', nb.math('MULTIPLY', edge, 0.35), 0.04)
    glow = nb.math('ADD', nb.math('MULTIPLY', veins, 0.45), thin)
    glow = nb.math('MULTIPLY', glow, nb.maprange(blot, 0.25, 0.75, 0.4, 1.0))
    emit = nb.mix(glow, (0, 0, 0), (0.55, 0.075, 0.012))
    rough = nb.math('ADD', 0.5, nb.math('MULTIPLY', wr, 0.2))
    return dict(color=col, rough=rough, metal=0.0, normal=nrm, emit=emit)


def m_bone(nb):
    co = nb.coord().outputs['Object']
    tip = nb.attr("tip").outputs['Factor']
    rings = nb.math('SINE', nb.math('MULTIPLY', tip, 70.0))
    n1 = nb.noise(co, 30.0, 4.0).outputs['Factor']
    n2 = nb.noise(nb.vscale(co, (1, 1, 6)), 6.0, 3.0).outputs['Factor']
    h = nb.math('ADD', nb.math('MULTIPLY', rings, 0.25), nb.math('MULTIPLY', n2, 0.6))
    h = nb.math('ADD', h, nb.math('MULTIPLY', n1, 0.2))
    nrm = nb.bump(h, 0.6, 0.006)
    col = nb.ramp(tip, [(0.0, (0.05, 0.035, 0.025)), (0.22, (0.26, 0.20, 0.13)),
                        (0.7, (0.46, 0.39, 0.27)), (0.93, (0.36, 0.30, 0.21)), (1.0, (0.10, 0.08, 0.06))])
    col = nb.mix(nb.math('MULTIPLY', n2, 0.45), col, (0.13, 0.095, 0.06))
    rough = nb.math('ADD', 0.35, nb.math('MULTIPLY', n1, 0.2))
    return dict(color=col, rough=rough, metal=0.0, normal=nrm)


def m_eye(nb):
    d = nb.attr("eyedir").outputs['Vector']
    x, y, z = nb.sep(d)
    ax = nb.math('ABSOLUTE', x)
    slit_w = nb.math('MULTIPLY', nb.math('SUBTRACT', 1.0, nb.math('ABSOLUTE', z)), 0.16)
    pupil = nb.math('LESS_THAN', ax, slit_w)
    front = nb.maprange(nb.math('ABSOLUTE', y), 0.55, 0.75)
    pupil = nb.math('MULTIPLY', pupil, front)
    r = nb.math('SQRT', nb.math('ADD', nb.math('MULTIPLY', x, x), nb.math('MULTIPLY', z, z)))
    stri = nb.noise(nb.vscale(d, (8, 8, 8)), 4.0, 3.0).outputs['Factor']
    iris = nb.ramp(r, [(0.0, (1.0, 0.55, 0.05)), (0.5, (0.95, 0.35, 0.02)), (0.85, (0.45, 0.07, 0.0)),
                       (1.0, (0.05, 0.01, 0.0))])
    iris = nb.mix(nb.math('MULTIPLY', stri, 0.4), iris, (1.0, 0.75, 0.2))
    col = nb.mix(pupil, iris, (0.0, 0.0, 0.0))
    emit = nb.mix(pupil, nb.mix(1.0, iris, (3.0, 1.6, 0.4), 'MULTIPLY'), (0, 0, 0))
    return dict(color=col, rough=0.05, metal=0.0, emit=emit)


def m_leather(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 25.0, 6.0, 0.6).outputs['Factor']
    n2 = nb.noise(co, 4.0, 3.0).outputs['Factor']
    stud = nb.voronoi(co, 9.0, 'F1', 0.0).outputs['Distance']
    studm = nb.maprange(stud, 0.06, 0.08, 1.0, 0.0)
    h = nb.math('ADD', nb.math('MULTIPLY', n1, 0.4), nb.math('MULTIPLY', studm, 1.0))
    nrm = nb.bump(h, 0.6, 0.008)
    col = nb.mix(nb.maprange(n2, 0.3, 0.7), (0.10, 0.045, 0.02), (0.20, 0.10, 0.05))
    col = nb.mix(nb.math('MULTIPLY', n1, 0.4), col, (0.05, 0.022, 0.01))
    col = nb.mix(studm, col, (0.35, 0.33, 0.30))
    rough = nb.mixf(studm, nb.math('ADD', 0.5, nb.math('MULTIPLY', n1, 0.25)), 0.3)
    return dict(color=col, rough=rough, metal=studm, normal=nrm)


def m_iron(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 18.0, 5.0).outputs['Factor']
    col = nb.mix(nb.maprange(n1, 0.4, 0.7), (0.12, 0.11, 0.10), (0.05, 0.035, 0.025))
    nrm = nb.bump(n1, 0.3, 0.005)
    return dict(color=col, rough=nb.math('ADD', 0.35, nb.math('MULTIPLY', n1, 0.3)), metal=0.9,
                normal=nrm)


def m_mouth(nb):
    co = nb.coord().outputs['Object']
    n1 = nb.noise(co, 12.0, 4.0).outputs['Factor']
    col = nb.mix(n1, (0.12, 0.015, 0.01), (0.25, 0.04, 0.02))
    return dict(color=col, rough=0.3, metal=0.0, normal=nb.bump(n1, 0.3, 0.004))


M_SCALES = dlib.pbr_material("SRC_Scales", m_scales)
M_MEMB = dlib.pbr_material("SRC_Membrane", m_membrane)
M_BONE = dlib.pbr_material("SRC_Bone", m_bone)
M_EYE = dlib.pbr_material("SRC_Eye", m_eye)
M_LEATHER = dlib.pbr_material("SRC_Leather", m_leather)
M_IRON = dlib.pbr_material("SRC_Iron", m_iron)
BODY_MATS = [M_SCALES, M_BONE, M_EYE, M_LEATHER, M_IRON]
MI_SC, MI_BONE, MI_EYE, MI_LEA, MI_IRON = range(5)

body = Acc()
wing = Acc()   # membranes (material 0) + wing bones (1) + claws (2)

# ============================================================================ main body loft
th_all = np.linspace(0, 2 * math.pi, NS, endpoint=False)
R = np.zeros((NR, NS, 3))
belly = np.zeros((NR, NS))
for i in range(NR):
    for j, th in enumerate(th_all):
        R[i, j] = section_pt(i, th)
        c = math.cos(th)
        belly[i, j] = sstep(0.45, 0.85, -c) * (1.0 - sstep(4.15, 4.45, BX[i]))
body.rings(R, closed=True, cap0=True, cap1=True, mat=MI_SC,
           weights=[body_w(BL[i]) for i in range(NR)],
           attrs={"belly": belly.ravel(), "along": np.repeat(BL, NS)})

# ---------------------------------------------------------------------------- jaw
def jaw_section(t, th, L):
    return 1.0
jaw_rows = [
    (4.36, 0, 1.49, 0.26, 0.10),
    (4.60, 0, 1.44, 0.30, 0.11),
    (4.95, 0, 1.36, 0.24, 0.10),
    (5.30, 0, 1.28, 0.16, 0.085),
    (5.52, 0, 1.23, 0.09, 0.06),
    (5.60, 0, 1.215, 0.02, 0.02),
]
jw = {"Jaw": 1.0}
loft(body, jaw_rows, 60, 40, mat=MI_SC, weight_fn=lambda t, L: jw,
     attrs={"belly": lambda t, L: 0.0, "along": lambda t, L: 0.0})
# throat plates under jaw via belly attribute on lower half: second thin loft underneath
loft(body, [(4.5, 0, 1.38, 0.2, 0.05), (4.9, 0, 1.29, 0.17, 0.05), (5.3, 0, 1.215, 0.11, 0.04),
            (5.5, 0, 1.18, 0.05, 0.02)], 30, 24, mat=MI_SC, weight_fn=lambda t, L: jw,
     attrs={"belly": lambda t, L: 1.0, "along": lambda t, L: L * 1.6})
# mouth interior (dark red) visible when the jaw opens
loft(body, [(4.45, 0, 1.47, 0.22, 0.03), (5.0, 0, 1.40, 0.18, 0.03), (5.45, 0, 1.31, 0.08, 0.02)],
     20, 20, mat=MI_SC, weight_fn=lambda t, L: {"Head": 0.6, "Jaw": 0.4},
     attrs={"belly": lambda t, L: 0.9, "along": lambda t, L: 0.0})


# ---------------------------------------------------------------------------- helpers
def spike(acc, base, direction, length, r0, mat, weights, bend=(0, 0, 0), n=10, seg=10,
          flat=1.0, up=(0, 0, 1), ridged=0.0, tipattr=True):
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    b = np.asarray(bend, float)
    rows = []
    for k, t in enumerate(np.linspace(0, 1, 5)):
        p = np.asarray(base) + d * length * t + b * length * t * t
        r = r0 * (1 - t) ** 0.9 + 0.002
        rows.append((p[0], p[1], p[2], r * flat, r))
    sec = None
    if ridged:
        sec = lambda t, th, L: 1.0 + ridged * math.sin(t * 2 * math.pi * 9)
    return loft(acc, rows, n, seg, up=up, cap0=True, cap1=False, mat=mat,
                weight_fn=lambda t, L: weights, section=sec,
                attrs={"tip": (lambda t, L: t)} if tipattr else None)


def head_w(x):
    return body_w(x2L(x))


# ---------------------------------------------------------------------------- horns, spikes, teeth
for sg in (1, -1):
    hb = surf(4.33, sg * 0.55, -0.03)
    rows = [(hb[0], hb[1], hb[2], 0.115, 0.115),
            (hb[0] - 0.32, hb[1] + sg * 0.10, hb[2] + 0.17, 0.095, 0.095),
            (hb[0] - 0.78, hb[1] + sg * 0.20, hb[2] + 0.24, 0.07, 0.07),
            (hb[0] - 1.18, hb[1] + sg * 0.26, hb[2] + 0.20, 0.045, 0.045),
            (hb[0] - 1.50, hb[1] + sg * 0.27, hb[2] + 0.34, 0.006, 0.006)]
    loft(body, rows, 90, 14, cap0=True, cap1=False, mat=MI_BONE, weight_fn=lambda t, L: {"Head": 1.0},
         section=lambda t, th, L: 1.0 + 0.13 * max(0.0, math.sin(t * 2 * math.pi * 13)) ** 2 * (1 - t),
         attrs={"tip": lambda t, L: t})
    hb2 = surf(4.55, sg * 1.05, -0.02)
    rows = [(hb2[0], hb2[1], hb2[2], 0.06, 0.06),
            (hb2[0] - 0.25, hb2[1] + sg * 0.14, hb2[2] + 0.02, 0.045, 0.045),
            (hb2[0] - 0.55, hb2[1] + sg * 0.22, hb2[2] + 0.07, 0.02, 0.02),
            (hb2[0] - 0.72, hb2[1] + sg * 0.24, hb2[2] + 0.15, 0.004, 0.004)]
    loft(body, rows, 24, 10, cap0=True, cap1=False, mat=MI_BONE, weight_fn=lambda t, L: {"Head": 1.0},
         attrs={"tip": lambda t, L: t})
    # cheek / jaw frill spikes
    for k, x in enumerate((4.38, 4.50, 4.62)):
        p = surf(x, sg * 1.9, -0.02)
        spike(body, p, (-1.0, sg * 0.6, -0.35 - 0.1 * k), 0.30 - 0.06 * k, 0.04, MI_BONE,
              {"Head": 1.0}, bend=(0, 0, 0.1))
    # brow spikes
    for k, x in enumerate((4.80, 4.90, 5.0)):
        p = surf(x, sg * 0.72, -0.01)
        spike(body, p, (-1.0, sg * 0.25, 0.55), 0.16 - 0.03 * k, 0.025, MI_BONE, {"Head": 1.0})
    # upper teeth along the lip
    for k, x in enumerate(np.linspace(4.88, 5.52, 8)):
        p = surf(x, sg * 2.25, -0.015)
        fang = abs(x - 5.33) < 0.05
        ln = 0.15 if fang else 0.06 + 0.02 * math.sin(k * 2.3)
        spike(body, p, (0.15, -sg * 0.1, -1.0), ln, 0.022 if fang else 0.012, MI_BONE, {"Head": 1.0},
              n=6, seg=8)
    # lower fangs
    for x in (5.40, 5.12):
        jz = np.interp(x, [r[0] for r in jaw_rows], [r[2] for r in jaw_rows])
        jwd = np.interp(x, [r[0] for r in jaw_rows], [r[3] for r in jaw_rows])
        p = (x, sg * jwd * 0.82, jz + 0.05)
        spike(body, p, (0.1, sg * 0.05, 1.0), 0.09, 0.016, MI_BONE, {"Jaw": 1.0}, n=6, seg=8)
    # chin barbs
    p = (5.0, sg * 0.12, 1.29)
    spike(body, p, (-0.5, sg * 0.3, -1.0), 0.14, 0.025, MI_BONE, {"Jaw": 1.0})
    # eyes
    ec = surf(4.99, sg * 1.10, -0.045)
    nrm = surf(4.99, sg * 1.10, 0.1) - ec
    nrm /= np.linalg.norm(nrm)
    er = 0.075
    fwd = np.cross(nrm, (0, 0, 1)) * (-sg)
    fwd /= np.linalg.norm(fwd)
    upv = np.cross(fwd, nrm) * (-sg) if False else np.cross(nrm, fwd)
    if upv[2] < 0:
        upv = -upv
    eye_rows = []
    for t in np.linspace(0, 1, 9):
        pt = ec - nrm * er + nrm * 2 * er * t
        r = er * math.sqrt(max(0.0, 1 - (2 * t - 1) ** 2)) + 1e-4
        eye_rows.append((pt[0], pt[1], pt[2], r, r))
    base_i = body.n
    loft(body, eye_rows, 18, 24, up=upv, cap0=True, cap1=True, mat=MI_EYE,
         weight_fn=lambda t, L: {"Head": 1.0})
    # eyedir attribute for the slit pupil
    vv = np.array(body.V[base_i:body.n])
    dd = (vv - ec) / er
    ed = np.stack([dd @ fwd, dd @ nrm, dd @ upv], 1)
    body.A.setdefault("eyedir", [(0.0, 0.0, 0.0)] * base_i)
    if len(body.A["eyedir"]) < body.n:
        body.A["eyedir"].extend([(0.0, 0.0, 0.0)] * (body.n - len(body.A["eyedir"])))
    for k in range(len(vv)):
        body.A["eyedir"][base_i + k] = tuple(ed[k])
# nose horn
p = surf(5.42, 0.0, -0.01)
spike(body, p, (0.45, 0, 1.0), 0.17, 0.035, MI_BONE, {"Head": 1.0}, bend=(-0.2, 0, 0))

# ---------------------------------------------------------------------------- dorsal spines
def spine_h(x):
    if 0.15 < x < 2.45:
        return 0.0          # saddle / rider zone
    if x >= 2.45:
        return 0.30 * sstep(2.45, 2.9, x) * (1 - 0.45 * sstep(3.3, 4.3, x))
    if x > -2.3:
        return 0.42 * sstep(0.15, -0.6, x)
    return 0.42 * (1 - sstep(-2.3, -5.6, x)) + 0.07
Ls = []
L = x2L(4.15)
while L > x2L(-5.7):
    Ls.append(L)
    x = float(np.interp(L, BL, BX))
    L -= 0.24 if x > 1.8 else 0.30
for L in Ls:
    x = float(np.interp(L, BL, BX))
    hgt = spine_h(x)
    if hgt <= 0.02:
        continue
    i_f = float(np.interp(L, BL, np.arange(NR)))
    p = section_pt(i_f, 0.0, -0.04)
    i0 = int(i_f)
    T, U = BT[i0], BU[i0]
    d = U * 1.0 - T * 0.75
    spike(body, p, d, hgt, hgt * 0.32, MI_BONE, body_w(L), bend=-T * 0.25, n=8, seg=10, flat=0.35)

# ---------------------------------------------------------------------------- tail spade
endp, endT = BC[0], -BT[0]
endT = endT / np.linalg.norm(endT)
prof = [(0, .045, .045), (.06, .11, .04), (.16, .30, .035), (.22, .34, .03), (.27, .27, .03),
        (.42, .24, .026), (.70, .12, .02), (.92, .03, .012), (1.0, .004, .004)]
rows = [tuple(endp + endT * (t * 0.62 - 0.05)) + (a, b) for t, a, b in prof]
loft(body, rows, 40, 24, cap0=True, cap1=False, mat=MI_BONE,
     weight_fn=lambda t, L: {"Tail10": 1.0},
     section=lambda t, th, L: 1.0 + 0.6 * math.exp(-((abs(math.cos(th)) - 1) / 0.12) ** 2) * 0.0,
     attrs={"tip": lambda t, L: 0.35 + 0.6 * t})

# ---------------------------------------------------------------------------- saddle + straps
SADDLE_X = 1.62   # base of the neck, between/just ahead of the wing roots
seat = None
nth = 28
xs = np.linspace(SADDLE_X - 0.36, SADDLE_X + 0.44, 26)
rings = []
for x in xs:
    i_f = x2i(x)
    top, bot = [], []
    thmax = 1.2 * (0.62 + 0.38 * math.sin(math.pi * (x - xs[0]) / 0.80) ** 0.6)
    for th in np.linspace(-thmax, thmax, nth):
        a = abs(th) / thmax
        o = 0.04 * (0.35 + 0.65 * (1 - a ** 4))
        o += 0.10 * sstep(SADDLE_X - 0.22, SADDLE_X - 0.36, x) * (1 - a ** 2)                          # cantle
        o += 0.10 * sstep(SADDLE_X + 0.30, SADDLE_X + 0.44, x) * math.exp(-(th / 0.45) ** 2)          # pommel
        o -= 0.015 * math.exp(-((x - SADDLE_X) / 0.2) ** 2) * (1 - a ** 2)       # seat dip
        top.append(section_pt(i_f, th, o))
        bot.append(section_pt(i_f, th, -0.02))
    rings.append(top + bot[::-1])
rings = np.array(rings)
body.rings(rings, closed=True, cap0=True, cap1=True, mat=MI_LEA,
           weights=[body_w(x2L(x)) for x in xs])
seat = section_pt(x2i(SADDLE_X), 0.0, 0.04 - 0.015)
# saddle horn (rider grip)
hp = section_pt(x2i(SADDLE_X + 0.40), 0.0, 0.08)
rows = [(hp[0], 0, hp[2] - 0.05, 0.05, 0.05), (hp[0] + 0.03, 0, hp[2] + 0.10, 0.035, 0.035),
        (hp[0] + 0.07, 0, hp[2] + 0.20, 0.04, 0.04), (hp[0] + 0.09, 0, hp[2] + 0.25, 0.06, 0.05),
        (hp[0] + 0.10, 0, hp[2] + 0.29, 0.001, 0.001)]
loft(body, rows, 16, 14, cap0=True, cap1=False, mat=MI_IRON, weight_fn=lambda t, L: body_w(x2L(SADDLE_X + 0.44)))
# girth straps (two), around the barrel
for x0 in (SADDLE_X - 0.08, SADDLE_X + 0.24):
    sx = [x0 - 0.065, x0 - 0.06, x0 + 0.06, x0 + 0.065]
    so = [-0.005, 0.014, 0.014, -0.005]
    rr = np.array([[section_pt(x2i(x), th, o) for th in th_all] for x, o in zip(sx, so)])
    body.rings(rr, closed=True, mat=MI_LEA, weights=[body_w(x2L(x)) for x in sx])
# a front chest strap ring (pommel to chest) - iron rings at strap crossings
for sg in (1, -1):
    for x0 in (SADDLE_X - 0.08, SADDLE_X + 0.24):
        c = section_pt(x2i(x0), sg * 1.25, 0.02)
        rows = [(c[0] - 0.04, c[1], c[2], 0.035, 0.035), (c[0] + 0.04, c[1], c[2], 0.035, 0.035)]
        loft(body, rows, 4, 12, mat=MI_IRON, weight_fn=lambda t, L, x0=x0: body_w(x2L(x0)))
SEAT = np.array(seat)
bone("Saddle", SEAT, SEAT + np.array((0, 0.3, 0)), "Spine04" if SADDLE_X > 0.9 else "Spine03")

# ============================================================================ legs
def limb(acc, sg, sfx, rows, names, jidx, toe_base, toe_dirs, parent_spine, flat_from=None):
    """rows: (x,y,z,ra,rb) for left side; names: chain bone names for segments between
    joint rows jidx (indices into rows)."""
    rr = [(x, sg * y, z, a, b) for (x, y, z, a, b) in rows]
    info = loft(acc, rr, 70, 26, up=(1, 0, 0), cap0=True, cap1=True, mat=MI_SC,
                attrs={"belly": lambda t, L: 0.0, "along": lambda t, L: 0.0})
    # weights after the fact (need ctrlL)
    J = [info['ctrlL'][k] for k in jidx]
    nm = [parent_spine] + [n + sfx for n in names]
    J = [0.0] + J[1:] if False else J
    L = info['L']
    start = acc.n - (70 * 26 + 2)
    for i in range(70):
        w = chain_weights(L[i], J, nm[:-1], blend=0.3)
        for j in range(26):
            acc.W[start + i * 26 + j] = w
    acc.W[start + 70 * 26] = {nm[0]: 1.0}
    acc.W[start + 70 * 26 + 1] = {nm[-2]: 1.0}
    # toes + claws
    tb = np.array((toe_base[0], sg * toe_base[1], toe_base[2]))
    toe_bone = nm[-1]
    for (dx, dy, dz, ln) in toe_dirs:
        d = np.array((dx, sg * dy, dz))
        d /= np.linalg.norm(d)
        p1 = tb + d * ln * 0.5 + np.array((0, 0, 0.03))
        p2 = tb + d * ln
        trows = [(tb[0], tb[1], tb[2] + 0.02, 0.07, 0.055), tuple(p1) + (0.055, 0.05), tuple(p2) + (0.04, 0.035)]
        loft(acc, trows, 12, 14, up=(0, 0, 1), cap0=True, cap1=True, mat=MI_SC,
             weight_fn=lambda t, L: {toe_bone: 1.0},
             attrs={"belly": lambda t, L: 0.0, "along": lambda t, L: 0.0})
        spike(acc, p2 + d * 0.02, d + np.array((0, 0, -0.6)), 0.15, 0.035, MI_BONE, {toe_bone: 1.0},
              bend=(0, 0, -0.5), n=8, seg=10, flat=0.7)
    return info


LEGS = {}
for sg, sfx in ((1, "_L"), (-1, "_R")):
    # front
    F = [(1.25, 0.40, 0.05, 0.30, 0.30), (1.28, 0.60, -0.12, 0.29, 0.30), (1.12, 0.70, -0.50, 0.21, 0.22),
         (0.95, 0.73, -0.85, 0.15, 0.16), (1.10, 0.71, -1.18, 0.12, 0.13), (1.22, 0.69, -1.42, 0.10, 0.11),
         (1.40, 0.69, -1.60, 0.11, 0.075)]
    limb(body, sg, sfx, F, ["Arm_Upper", "Arm_Lower", "Hand", "FrontToes"], [0, 1, 3, 5, 6],
         (1.40, 0.69, -1.62), [(1, 0.25, -0.15, 0.30), (1, 0, -0.2, 0.34), (1, -0.25, -0.15, 0.28),
                               (-0.6, 0.1, -0.3, 0.16)], "Spine04")
    bone("Arm_Upper" + sfx, (1.28, sg * 0.60, -0.12), (0.95, sg * 0.73, -0.85), "Spine04")
    bone("Arm_Lower" + sfx, (0.95, sg * 0.73, -0.85), (1.22, sg * 0.69, -1.42), "Arm_Upper" + sfx)
    bone("Hand" + sfx, (1.22, sg * 0.69, -1.42), (1.40, sg * 0.69, -1.60), "Arm_Lower" + sfx)
    bone("FrontToes" + sfx, (1.40, sg * 0.69, -1.60), (1.72, sg * 0.69, -1.70), "Hand" + sfx)
    # hind
    H = [(-1.55, 0.38, 0.10, 0.42, 0.45), (-1.50, 0.62, -0.08, 0.44, 0.48), (-1.18, 0.78, -0.45, 0.28, 0.30),
         (-0.98, 0.83, -0.72, 0.18, 0.19), (-1.30, 0.80, -1.00, 0.14, 0.15), (-1.58, 0.78, -1.25, 0.11, 0.12),
         (-1.45, 0.78, -1.48, 0.10, 0.10), (-1.28, 0.78, -1.64, 0.11, 0.075)]
    limb(body, sg, sfx, H, ["Leg_Thigh", "Leg_Shin", "Leg_Foot", "Leg_Toes"], [0, 1, 3, 5, 7],
         (-1.28, 0.78, -1.66), [(1, 0.28, -0.12, 0.34), (1, 0, -0.2, 0.40), (1, -0.28, -0.12, 0.32),
                                (-0.8, 0.1, -0.2, 0.18)], "Spine01")
    bone("Leg_Thigh" + sfx, (-1.50, sg * 0.62, -0.08), (-0.98, sg * 0.83, -0.72), "Spine01")
    bone("Leg_Shin" + sfx, (-0.98, sg * 0.83, -0.72), (-1.58, sg * 0.78, -1.25), "Leg_Thigh" + sfx)
    bone("Leg_Foot" + sfx, (-1.58, sg * 0.78, -1.25), (-1.28, sg * 0.78, -1.64), "Leg_Shin" + sfx)
    bone("Leg_Toes" + sfx, (-1.28, sg * 0.78, -1.64), (-0.92, sg * 0.78, -1.72), "Leg_Foot" + sfx)

# ============================================================================ wings
WMI_MEMB, WMI_SC, WMI_BONE = 0, 1, 2


def finger_w(name, sfx, s, sk, b=0.12):
    a, c = f"{name}_01{sfx}", f"{name}_02{sfx}"
    if s < 0.08:
        t = s / 0.08
        return wmix((1 - t, {"Wing_Wrist" + sfx: 1.0}), (t, {a: 1.0}))
    if s < sk - b:
        return {a: 1.0}
    if s > sk + b:
        return {c: 1.0}
    t = (s - (sk - b)) / (2 * b)
    return {a: 1 - t, c: t}


for sg, sfx in ((1, "_L"), (-1, "_R")):
    def Y(p):
        return np.array((p[0], sg * p[1], p[2]), float)
    S0, S1, E, W = Y((1.42, 0.30, 0.55)), Y((1.50, 0.74, 0.80)), Y((1.05, 2.25, 1.05)), Y((1.65, 4.55, 1.10))
    FING = {
        "Wing_F1": (Y((1.45, 6.60, 1.12)), Y((0.80, 8.95, 1.02))),
        "Wing_F2": (Y((0.40, 6.15, 1.07)), Y((-1.05, 7.75, 0.95))),
        "Wing_F3": (Y((-0.42, 5.45, 1.01)), Y((-2.35, 6.25, 0.88))),
        "Wing_F4": (Y((-0.85, 4.72, 0.95)), Y((-3.15, 4.55, 0.82))),
    }
    bone("Wing_Shoulder" + sfx, S0, S1, "Spine04")
    bone("Wing_UpperArm" + sfx, S1, E, "Wing_Shoulder" + sfx)
    bone("Wing_Forearm" + sfx, E, W, "Wing_UpperArm" + sfx)
    wdir = (FING["Wing_F1"][0] - W)
    bone("Wing_Wrist" + sfx, W, W + wdir / np.linalg.norm(wdir) * 0.3, "Wing_Forearm" + sfx)
    for fn, (K, Tp) in FING.items():
        bone(fn + "_01" + sfx, W, K, "Wing_Wrist" + sfx)
        bone(fn + "_02" + sfx, K, Tp, fn + "_01" + sfx)
    # arm tube
    arm_rows = [tuple(S0) + (0.16, 0.16), tuple(S1) + (0.15, 0.15), tuple((S1 + E) / 2) + (0.10, 0.11),
                tuple(E) + (0.13, 0.13), tuple(E + (W - E) * 0.5) + (0.08, 0.085), tuple(W) + (0.12, 0.12),
                tuple(W + (W - E) / np.linalg.norm(W - E) * 0.12) + (0.06, 0.06)]
    info = loft(wing, arm_rows, 80, 18, cap0=True, cap1=True, mat=WMI_SC,
                attrs={"belly": lambda t, L: 0.0, "along": lambda t, L: 0.0, "edge": lambda t, L: 0.0})
    J = [info['ctrlL'][k] for k in (0, 1, 3, 5, 6)]
    nm = ["Wing_Shoulder" + sfx, "Wing_UpperArm" + sfx, "Wing_Forearm" + sfx, "Wing_Wrist" + sfx]
    st = wing.n - (80 * 18 + 2)
    for i in range(80):
        w = chain_weights(info['L'][i], J, nm, blend=0.25)
        for j in range(18):
            wing.W[st + i * 18 + j] = w
    wing.W[st + 80 * 18] = {nm[0]: 1.0}
    wing.W[st + 80 * 18 + 1] = {nm[-1]: 1.0}
    # thumb claw
    spike(wing, W + Y((0.05, 0.0, 0.03)), Y((1.0, 0.15, 0.1)), 0.32, 0.06, WMI_BONE,
          {"Wing_Wrist" + sfx: 1.0}, bend=Y((0, 0, -0.6)), n=10, seg=10)
    # fingers
    fcurves = {}
    for fn, (K, Tp) in FING.items():
        rows = [tuple(W) + (0.075, 0.075), tuple(K) + (0.06, 0.065), tuple(K + (Tp - K) * 0.55) + (0.035, 0.04),
                tuple(Tp) + (0.01, 0.01)]
        bow = np.cross(Tp - W, (0, 0, 1))
        info = loft(wing, rows, 50, 12, cap0=True, cap1=False, mat=WMI_SC,
                    attrs={"belly": lambda t, L: 0.0, "along": lambda t, L: 0.0, "edge": lambda t, L: 0.0})
        st = wing.n - 50 * 12 - 1
        sk = info['ctrlL'][1] / info['L'][-1]
        for i in range(50):
            w = finger_w(fn, sfx, info['L'][i] / info['L'][-1], sk)
            for j in range(12):
                wing.W[st + i * 12 + j] = w
        wing.W[st + 50 * 12] = finger_w(fn, sfx, 0.0, sk)
        fcurves[fn] = (info['C'], sk)
        if fn == "Wing_F1":
            spike(wing, Tp, Tp - K, 0.12, 0.02, WMI_BONE, {fn + "_02" + sfx: 1.0}, bend=Y((0, 0, -0.4)), n=6, seg=8)

    def fpt(fn, s):
        C, _ = fcurves[fn]
        idx = s * (len(C) - 1)
        i0 = int(min(idx, len(C) - 2))
        f = idx - i0
        return C[i0] * (1 - f) + C[i0 + 1] * f

    # membrane panels between fingers (scalloped trailing edge, cambered)
    NU, NV = 22, 30
    order = ["Wing_F1", "Wing_F2", "Wing_F3", "Wing_F4"]
    for a, b in zip(order[:-1], order[1:]):
        P = np.zeros((NV, NU, 3))
        Wt, edge = [], np.zeros((NV, NU))
        Ta, Tb = fpt(a, 1.0), fpt(b, 1.0)
        nrm = np.cross(Ta - W, Tb - W)
        nrm *= sg
        nrm /= np.linalg.norm(nrm)
        if nrm[2] < 0:
            nrm = -nrm
        ska, skb = fcurves[a][1], fcurves[b][1]
        for vi, s in enumerate(np.linspace(0.03, 1.0, NV)):
            for ui, u in enumerate(np.linspace(0, 1, NU)):
                se = s * (1 - 0.20 * math.sin(math.pi * u) ** 0.85)
                p = (1 - u) * fpt(a, se) + u * fpt(b, se)
                p = p + nrm * 0.16 * math.sin(math.pi * u) * math.sin(math.pi * min(se * 1.1, 1.0)) * se
                P[vi, ui] = p
                Wt.append(wmix((1 - u, finger_w(a, sfx, se, ska)), (u, finger_w(b, sfx, se, skb))))
                edge[vi, ui] = sstep(0.7, 1.0, s) * math.sin(math.pi * u) ** 0.5
        wing.grid(P, mat=WMI_MEMB, weights=Wt, attrs={"edge": edge.ravel()})
    # inner panel: arm (W->E->S1->front flank) vs trailing edge (F4 tip -> hip)
    A0 = surf(1.15, sg * 1.62, -0.03)
    H0 = surf(-1.95, sg * 1.62, -0.03)
    arm_path = np.array([W, (W + E) / 2, E, (E + S1) / 2, S1, A0])
    arm_names = [{"Wing_Wrist" + sfx: 0.5, "Wing_Forearm" + sfx: 0.5}, {"Wing_Forearm" + sfx: 1.0},
                 {"Wing_UpperArm" + sfx: 0.5, "Wing_Forearm" + sfx: 0.5}, {"Wing_UpperArm" + sfx: 1.0},
                 {"Wing_UpperArm" + sfx: 0.4, "Wing_Shoulder" + sfx: 0.6}, {"Spine04": 0.7, "Spine03": 0.3}]
    seglen = np.linalg.norm(np.diff(arm_path, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seglen)]) / seglen.sum()
    NT, NVv = 44, 26
    P = np.zeros((NT, NVv, 3))
    Wt, edge = [], np.zeros((NT, NVv))
    T4 = fpt("Wing_F4", 1.0)
    sk4 = fcurves["Wing_F4"][1]
    for ti, t in enumerate(np.linspace(0, 1, NT)):
        k = min(int(np.searchsorted(cum, t, side='right') - 1), len(arm_path) - 2)
        f = (t - cum[k]) / (cum[k + 1] - cum[k])
        c0 = arm_path[k] * (1 - f) + arm_path[k + 1] * f
        w0 = wmix((1 - f, arm_names[k]), (f, arm_names[k + 1]))
        c1 = T4 * (1 - t) + H0 * t
        c1 = c1 + (c0 - c1) * 0.20 * math.sin(math.pi * t) ** 0.8
        w1 = wmix((1 - t, {"Wing_F4_02" + sfx: 1.0}), (t, {"Spine02": 0.5, "Spine01": 0.5}))
        corr = (1 - sstep(0.0, 0.35, t))
        for vi, v in enumerate(np.linspace(0, 1, NVv)):
            p = c0 * (1 - v) + c1 * v
            if corr > 0:   # follow the bowed F4 finger exactly at the shared edge (no gap)
                p = p + corr * (fpt("Wing_F4", v) - (W * (1 - v) + T4 * v))
            bill = 0.32 * math.sin(math.pi * v) * math.sin(math.pi * t) ** 0.7
            p = p + np.array((0, 0, 1)) * bill
            P[ti, vi] = p
            wl = wmix((1 - v, w0), (v, w1))
            if t < 0.12:
                g = t / 0.12
                wl = wmix((1 - g, finger_w("Wing_F4", sfx, v, sk4)), (g, wl))
            Wt.append(wl)
            edge[ti, vi] = sstep(0.75, 1.0, v) * math.sin(math.pi * t) ** 0.4
    wing.grid(P, mat=WMI_MEMB, weights=Wt, attrs={"edge": edge.ravel()})
    # front panel (propatagium): neck base -> wrist leading edge, in front of the arm
    N0 = S1 + (E - S1) * 0.40      # leading flap starts on the upper arm (keeps the rider's legs clear)
    front_path = np.array([S1, (S1 + E) / 2, E, (E + W) / 2, W])
    fw = [{"Wing_Shoulder" + sfx: 0.6, "Wing_UpperArm" + sfx: 0.4}, {"Wing_UpperArm" + sfx: 1.0},
          {"Wing_UpperArm" + sfx: 0.5, "Wing_Forearm" + sfx: 0.5}, {"Wing_Forearm" + sfx: 1.0},
          {"Wing_Forearm" + sfx: 0.5, "Wing_Wrist" + sfx: 0.5}]
    seglen = np.linalg.norm(np.diff(front_path, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seglen)]) / seglen.sum()
    NT, NVv = 30, 10
    P = np.zeros((NT, NVv, 3))
    Wt = []
    for ti, t in enumerate(np.linspace(0, 1, NT)):
        k = min(int(np.searchsorted(cum, t, side='right') - 1), len(front_path) - 2)
        f = (t - cum[k]) / (cum[k + 1] - cum[k])
        c0 = front_path[k] * (1 - f) + front_path[k + 1] * f
        w0 = wmix((1 - f, fw[k]), (f, fw[k + 1]))
        lead = N0 * (1 - t) + W * t
        c1 = lead + (c0 - lead) * 0.15 * math.sin(math.pi * t)
        w1 = wmix((1 - t, {"Wing_UpperArm" + sfx: 1.0}), (t, {"Wing_Wrist" + sfx: 1.0}))
        for vi, v in enumerate(np.linspace(0, 1, NVv)):
            P[ti, vi] = c0 * (1 - v) + c1 * v + np.array((0, 0, 0.05)) * math.sin(math.pi * v)
            Wt.append(wmix((1 - v, w0), (v, w1)))
    wing.grid(P, mat=WMI_MEMB, weights=Wt, attrs={"edge": np.zeros(NT * NVv)})

# ============================================================================ build objects
ob_body = body.build("DragonBody", BODY_MATS)
ob_wing = wing.build("DragonWings", [M_MEMB, M_SCALES, M_BONE])
print(f"geometry built {time.time() - T0:.1f}s  body verts {len(ob_body.data.vertices)} wing verts {len(ob_wing.data.vertices)}")

# sculpt-like surface noise on the scaled parts (muscle/lump variation)
tex = bpy.data.textures.new("lumps", 'CLOUDS')
tex.noise_scale = 0.35
tex.noise_depth = 3
vg = ob_body.vertex_groups.new(name="_displace")
idx = [p.vertices[k] for p in ob_body.data.polygons if p.material_index == MI_SC for k in range(len(p.vertices))]
vg.add(list(set(idx)), 1.0, 'REPLACE')
md = ob_body.modifiers.new("lumps", 'DISPLACE')
md.texture = tex
md.strength = 0.03
md.mid_level = 0.5
md.vertex_group = "_displace"
md.texture_coords = 'OBJECT'
dlib.apply_modifiers(ob_body)
ob_body.vertex_groups.remove(ob_body.vertex_groups["_displace"])

# ============================================================================ centre of mass -> origin
def com_of(ob):
    me = ob.data
    me.calc_loop_triangles()
    v = np.array([x.co[:] for x in me.vertices])
    tri = np.array([t.vertices[:] for t in me.loop_triangles])
    a, b, c = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
    vol = np.einsum('ij,ij->i', a, np.cross(b, c)) / 6.0
    cen = (a + b + c) / 4.0
    return (cen * vol[:, None]).sum(0) / vol.sum(), vol.sum()


COM, VOL = com_of(ob_body)
print("centre of mass (pre-shift)", COM, "volume m3", VOL)
SHIFT = Matrix.Translation(Vector((-COM[0], -COM[1], -COM[2])))
COM_V = Vector(COM)
for ob in (ob_body, ob_wing):
    ob.data.transform(SHIFT)

# ============================================================================ armature
arm_data = bpy.data.armatures.new("DragonRig")
arm = bpy.data.objects.new("DragonRig", arm_data)
sc.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
for name, (h, t, par) in BONES.items():
    eb = arm_data.edit_bones.new(name)
    eb.head = Vector(h) - COM_V if name not in ("Root", "Body") else Vector(h)
    eb.tail = Vector(t) - COM_V if name not in ("Root", "Body") else Vector(t)
    d = (eb.tail - eb.head).normalized()
    eb.align_roll(Vector((0, 0, 1)) if abs(d.z) < 0.8 else Vector((1, 0, 0)))
for name, (h, t, par) in BONES.items():
    if par:
        eb = arm_data.edit_bones[name]
        eb.parent = arm_data.edit_bones[par]
        eb.use_connect = False
for b in arm_data.edit_bones:
    b.use_deform = b.name not in ("Root", "Saddle")
bpy.ops.object.mode_set(mode='OBJECT')
arm_data.display_type = 'STICK'
SEAT_LOCAL = Vector(SEAT) - COM_V
print("Saddle (m, rel. origin, Blender +X fwd +Y left +Z up):", tuple(round(v, 3) for v in SEAT_LOCAL))

# ============================================================================ bake
if not NOBAKE:
    tb = time.time()
    dlib.smart_uv(ob_body, 60.0, 0.002)
    dlib.smart_uv(ob_wing, 60.0, 0.002)
    print(f"uv done {time.time() - tb:.1f}s", flush=True)
    pb = dlib.bake_object(ob_body, "Dragon_Body", BODY_TEX)
    pb = dlib.pack_orm(pb, "Dragon_Body")
    pw = dlib.bake_object(ob_wing, "Dragon_Wings", WING_TEX)
    pw = dlib.pack_orm(pw, "Dragon_Wings")
    print(f"bake done {time.time() - tb:.1f}s", flush=True)
    MF_BODY = dlib.final_material("M_Dragon_Body", pb)
    MF_WING = dlib.final_material("M_Dragon_Wings", pw)
else:
    MF_BODY, MF_WING = M_SCALES, M_MEMB


def collapse_materials(ob, mat):
    me = ob.data
    me.polygons.foreach_set("material_index", [0] * len(me.polygons))
    me.materials.clear()
    me.materials.append(mat)


# thin membranes: separate membrane faces, solidify (2.5 cm), rejoin
bpy.ops.object.select_all(action='DESELECT')
ob_wing.select_set(True)
bpy.context.view_layer.objects.active = ob_wing
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
for p in ob_wing.data.polygons:
    p.select = p.material_index == WMI_MEMB
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.separate(type='SELECTED')
bpy.ops.object.mode_set(mode='OBJECT')
memb = [o for o in bpy.context.selected_objects if o != ob_wing][0]
memb.name = "DragonMembranes"
so = memb.modifiers.new("thick", 'SOLIDIFY')
so.thickness = 0.025
so.offset = 0.0
so.use_even_offset = True
so.use_rim = True
dlib.apply_modifiers(memb)
if not NOBAKE:
    collapse_materials(ob_body, MF_BODY)
    collapse_materials(ob_wing, MF_WING)
    collapse_materials(memb, MF_WING)
bpy.ops.object.select_all(action='DESELECT')
for o in (ob_wing, memb, ob_body):
    o.select_set(True)
bpy.context.view_layer.objects.active = ob_body
bpy.ops.object.join()
dragon = ob_body
dragon.name = "Dragon"
dragon.data.name = "Dragon"
if MF_WING not in list(dragon.data.materials):
    dragon.data.materials.append(MF_WING)
# keep only the two final material slots
bpy.ops.object.material_slot_remove_unused()
# drop helper attributes not needed downstream
for nm in ("belly", "along", "edge", "tip", "eyedir"):
    a = dragon.data.attributes.get(nm)
    if a and not NOBAKE:
        dragon.data.attributes.remove(a)

# normalise weights, limit 4 influences
bpy.ops.object.select_all(action='DESELECT')
dragon.select_set(True)
bpy.context.view_layer.objects.active = dragon
bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL', lock_active=False)

dragon.parent = arm
mod = dragon.modifiers.new("DragonRig", 'ARMATURE')
mod.object = arm
print("TRIANGLES dragon:", dlib.tri_count(dragon))

# ============================================================================ animation
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dragon_anims.py"), encoding="utf8").read())

out = os.path.join(dlib.OUT_DIR, "Dragon.blend")
bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
print(f"saved {out}  total {time.time() - T0:.1f}s")
