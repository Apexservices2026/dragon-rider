"""Procedural DragonRig actions. Exec'd by build_dragon.py (needs `arm`, `dlib`).
Can also be re-run on its own against Dragon.blend:
  blender -b Game/DragonRider/Saved/Generated/Dragon/Dragon.blend -P tools/blender/dragon/dragon_anims.py -- --save

All rotations are written as (world_axis, angle) relative to the rest pose for the LEFT
side and mirrored for the right. Axis conventions (Blender, dragon faces +X):
  'x' about the body axis  -> left wing up (+), 'z' vertical -> sweep back (+),
  'y' lateral -> pitch nose-down / leg swing back (+), 'b' about the bone's own axis.
Loops are pure functions of phase with integer harmonics => seamless (last key == first).
"""
import math
import bpy
from mathutils import Vector

try:
    arm  # noqa: F821  (provided by build_dragon.py)
except NameError:  # standalone
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import dlib  # noqa: F401
    arm = bpy.data.objects["DragonRig"]
    for a in list(bpy.data.actions):
        if a.name in ("Flap", "Glide", "DiveTuck", "WingBeatStrong", "Hover"):
            bpy.data.actions.remove(a)

PAIRED = ["Wing_Shoulder", "Wing_UpperArm", "Wing_Forearm", "Wing_Wrist"] + \
         [f"Wing_F{i}_{s}" for i in range(1, 5) for s in ("01", "02")] + \
         ["Arm_Upper", "Arm_Lower", "Hand", "FrontToes", "Leg_Thigh", "Leg_Shin", "Leg_Foot", "Leg_Toes"]
FOLD_F01 = {1: 1.19, 2: 0.77, 3: 0.31, 4: 0.03}


def add(p, bone, *rots):
    p.setdefault(bone, []).extend(rots)


TUCK_F = {1: 0.35, 2: -0.09, 3: -0.56, 4: -0.87}


def wing(p, lift=0.07, sweep=0.0, fold=0.0, fore_lift=0.0, fing_lift=0.0, fing2_lift=None,
         twist=0.0, ripple=None, tuck=0.0):
    """fold: bat-style elbow/wrist fold (used partially on upstrokes).
    tuck: dive pose, wings swept back into an arrowhead and lowered along the flanks."""
    add(p, "Wing_UpperArm", ('z', sweep + 0.77 * fold + 0.68 * tuck), ('x', lift - 0.45 * fold - 0.42 * tuck))
    add(p, "Wing_Forearm", ('z', -2.16 * fold + 0.87 * tuck), ('x', fore_lift - 0.05 * tuck), ('b', twist))
    add(p, "Wing_Wrist", ('z', 1.57 * fold - 0.30 * tuck), ('x', fing_lift - 0.06 * tuck))
    for k in range(1, 5):
        add(p, f"Wing_F{k}_01", ('z', FOLD_F01[k] * fold - 0.04 * (k - 2.5) * fold + TUCK_F[k] * tuck),
            ('x', -0.03 * k * fold - 0.02 * k * tuck))
        l2 = fing2_lift if fing2_lift is not None else 0.0
        if ripple:
            l2 += ripple(k)
        add(p, f"Wing_F{k}_02", ('x', l2 * (1 - fold)), ('z', 0.05 * fold - 0.05 * tuck))


def legs_tucked(p, amt=1.0):
    add(p, "Arm_Upper", ('y', 0.95 * amt))
    add(p, "Arm_Lower", ('y', -1.95 * amt))
    add(p, "Hand", ('y', 1.35 * amt))
    add(p, "FrontToes", ('y', 0.5 * amt))
    add(p, "Leg_Thigh", ('y', 1.15 * amt))
    add(p, "Leg_Shin", ('y', 0.55 * amt))
    add(p, "Leg_Foot", ('y', 0.45 * amt))
    add(p, "Leg_Toes", ('y', 0.6 * amt))


def neck_posture(p, a=1.0):
    add(p, "Neck01", ('y', 0.22 * a))
    add(p, "Neck02", ('y', 0.06 * a))
    add(p, "Neck04", ('y', -0.06 * a))
    add(p, "Neck05", ('y', -0.12 * a))
    add(p, "Head", ('y', -0.08 * a))


def warp(ph):
    """Downstroke (0..pi) takes ~41% of the cycle."""
    return ph + 0.3 * (1 - math.cos(ph))


# ----------------------------------------------------------------------------- Flap
def flap(f, ph):
    w = warp(ph)
    p = {}
    fold = 0.30 * (0.5 - 0.5 * math.sin(w - 0.3))
    wing(p, lift=0.15 + 0.80 * math.cos(w), sweep=-0.18 * math.sin(w), fold=fold,
         fore_lift=0.24 * math.cos(w - 0.7), fing_lift=0.18 * math.cos(w - 1.3),
         fing2_lift=0.16 * math.cos(w - 1.9), twist=0.12 * math.sin(w - 0.3))
    add(p, "Wing_Shoulder", ('x', 0.10 * math.cos(w + 0.2)))
    p["Body@loc"] = Vector((0, 0, -0.11 * math.cos(w - 0.3)))
    add(p, "Body", ('y', 0.035 * math.sin(w - 0.2)))
    neck_posture(p)
    for i in range(1, 7):
        add(p, f"Neck{i:02d}", ('y', 0.035 * math.sin(w - 0.5 - 0.35 * i)), ('z', 0.012 * math.sin(ph - 0.4 * i)))
    add(p, "Head", ('y', -0.07 * math.sin(w - 2.6)))
    add(p, "Jaw", ('y', 0.03 + 0.03 * math.sin(w - 2.0)))
    for i in range(1, 11):
        add(p, f"Tail{i:02d}", ('y', -0.05 * math.sin(w - 0.9 - 0.45 * i)),
            ('z', 0.025 * (1 + 0.1 * i) * math.sin(ph - 0.5 * i)))
    legs_tucked(p)
    add(p, "Leg_Shin", ('y', 0.04 * math.sin(w - 1.5)))
    return p


# ----------------------------------------------------------------------------- Glide
def glide(f, ph):
    p = {}
    wing(p, lift=0.07 + 0.025 * math.sin(ph), sweep=0.02 * math.sin(ph + 1.0),
         fore_lift=0.03 * math.sin(ph - 0.6), fing_lift=0.02 * math.sin(ph - 1.0),
         twist=0.025 * math.sin(ph),
         ripple=lambda k: 0.03 * math.sin(2 * ph - 0.8 * k) + 0.012 * math.sin(5 * ph + k))
    p["Body@loc"] = Vector((0, 0, 0.04 * math.sin(ph)))
    add(p, "Body", ('y', -0.012 * math.sin(ph - 0.5)), ('x', 0.02 * math.sin(ph + 0.3)))
    add(p, "Spine03", ('y', 0.012 * math.sin(2 * ph)))      # breathing
    add(p, "Spine04", ('y', -0.015 * math.sin(2 * ph)))
    neck_posture(p)
    for i in range(1, 7):
        add(p, f"Neck{i:02d}", ('z', 0.035 * math.sin(ph + 0.6 - 0.3 * i)),
            ('y', 0.015 * math.sin(2 * ph - 0.4 * i)))
    add(p, "Head", ('z', -0.06 * math.sin(ph - 1.2)), ('y', 0.02 * math.sin(2 * ph - 2.6)))
    add(p, "Jaw", ('y', 0.02 + 0.02 * math.sin(2 * ph)))
    for i in range(1, 11):
        add(p, f"Tail{i:02d}", ('z', 0.03 * (1 + 0.22 * i) * math.sin(ph - 0.45 * i)),
            ('y', 0.015 * math.sin(ph - 0.3 * i)))
    legs_tucked(p)
    return p


# ----------------------------------------------------------------------------- DiveTuck
def dive(f, ph):
    p = {}
    wing(p, lift=0.0 + 0.01 * math.sin(6 * ph), tuck=1.0, fore_lift=0.012 * math.sin(9 * ph),
         fing_lift=0.01 * math.sin(9 * ph + 1.3), twist=0.01 * math.sin(6 * ph + 0.7))
    add(p, "Wing_Shoulder", ('x', -0.08), ('z', 0.05))
    add(p, "Body", ('x', 0.01 * math.sin(3 * ph)))
    for i, a in enumerate((0.35, 0.20, 0.05, 0.0, -0.15, -0.2), start=1):
        add(p, f"Neck{i:02d}", ('y', a), ('z', 0.006 * math.sin(6 * ph - 0.5 * i)))
    add(p, "Head", ('y', -0.22), ('z', 0.01 * math.sin(3 * ph)))
    for i in range(1, 11):
        add(p, f"Tail{i:02d}", ('z', 0.01 * math.sin(3 * ph - 0.5 * i) + 0.004 * math.sin(12 * ph - i)),
            ('y', -0.01))
    legs_tucked(p, 1.05)
    return p


# ----------------------------------------------------------------------------- WingBeatStrong (one-shot)
def _interp(keys, t):
    t = min(max(t, 0.0), 1.0)
    for (t0, v0), (t1, v1) in zip(keys[:-1], keys[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            u = 0.5 - 0.5 * math.cos(math.pi * u)
            return v0 + (v1 - v0) * u
    return keys[-1][1]


BEAT = [(0.0, 0.07), (0.30, 1.08), (0.62, -0.82), (1.0, 0.07)]


def _bump(t, a, b):
    if t <= a or t >= b:
        return 0.0
    return math.sin(math.pi * (t - a) / (b - a))


def beat(f, ph, N=40):
    t = f / N
    p = {}
    lift = _interp(BEAT, t)
    fl = 0.35 * (_interp(BEAT, t - 0.06) - lift)
    gl = 0.35 * (_interp(BEAT, t - 0.11) - _interp(BEAT, t - 0.06))
    g2 = 0.3 * (_interp(BEAT, t - 0.16) - _interp(BEAT, t - 0.11))
    wing(p, lift=lift, sweep=-0.28 * _bump(t, 0.3, 0.66) + 0.12 * _bump(t, 0.05, 0.3),
         fold=0.35 * _bump(t, 0.04, 0.32), fore_lift=fl, fing_lift=gl, fing2_lift=g2,
         twist=0.15 * _bump(t, 0.3, 0.62))
    add(p, "Wing_Shoulder", ('x', 0.12 * (lift - 0.07)))
    rise = math.sin(math.pi * dlib.sstep(0.32, 1.0, t))
    p["Body@loc"] = Vector((0, 0, 0.28 * rise - 0.06 * _bump(t, 0.0, 0.35)))
    add(p, "Body", ('y', -0.14 * math.sin(math.pi * t)))
    neck_posture(p)
    for i in range(1, 7):
        add(p, f"Neck{i:02d}", ('y', 0.06 * _bump(t, 0.25 + 0.03 * i, 0.85 + 0.02 * i)))
    add(p, "Head", ('y', 0.08 * _bump(t, 0.3, 0.9)))
    add(p, "Jaw", ('y', 0.02 + 0.10 * _bump(t, 0.35, 0.8)))
    for i in range(1, 11):
        add(p, f"Tail{i:02d}", ('y', -0.06 * _bump(t, 0.25 + 0.03 * i, 0.75 + 0.025 * i) +
                                0.03 * _bump(t, 0.0, 0.3)))
    legs_tucked(p)
    add(p, "Leg_Thigh", ('y', -0.15 * _bump(t, 0.3, 0.9)))
    return p


# ----------------------------------------------------------------------------- Hover
def hover(f, ph):
    w = warp(ph)
    p = {}
    wing(p, lift=0.15 + 0.62 * math.cos(w), sweep=-0.45 * math.sin(w),
         fold=0.32 * (0.5 - 0.5 * math.sin(w - 0.3)), fore_lift=0.2 * math.cos(w - 0.7),
         fing_lift=0.15 * math.cos(w - 1.3), fing2_lift=0.14 * math.cos(w - 1.9),
         twist=0.30 * math.sin(w))
    add(p, "Body", ('y', -0.55 + 0.03 * math.sin(w - 0.4)))
    p["Body@loc"] = Vector((0, 0, -0.07 * math.cos(w - 0.3)))
    for i, a in enumerate((0.25, 0.15, 0.1, 0.05, 0.0, 0.0), start=1):
        add(p, f"Neck{i:02d}", ('y', a + 0.03 * math.sin(w - 0.5 - 0.35 * i)),
            ('z', 0.03 * math.sin(ph - 0.3 * i)))
    add(p, "Head", ('y', 0.12 - 0.05 * math.sin(w - 2.6)), ('z', -0.05 * math.sin(ph - 2.0)))
    add(p, "Jaw", ('y', 0.06 + 0.06 * math.sin(ph)))
    for i in range(1, 11):
        add(p, f"Tail{i:02d}", ('y', -0.045 + 0.03 * math.sin(w - 1.0 - 0.45 * i)),
            ('z', 0.05 * (1 + 0.1 * i) * math.sin(ph - 0.4 * i)))
    add(p, "Arm_Upper", ('y', -0.25 + 0.05 * math.sin(w - 1.2)))
    add(p, "Arm_Lower", ('y', -0.55))
    add(p, "Hand", ('y', 0.5 + 0.08 * math.sin(w - 1.8)))
    add(p, "Leg_Thigh", ('y', -0.35 + 0.04 * math.sin(w - 1.4)))
    add(p, "Leg_Shin", ('y', 0.35))
    add(p, "Leg_Foot", ('y', 0.25 + 0.06 * math.sin(w - 2.0)))
    add(p, "Leg_Toes", ('y', 0.3))
    return p


ACTIONS = [("Flap", 27, flap, True), ("Glide", 105, glide, True), ("DiveTuck", 45, dive, True),
           ("WingBeatStrong", 40, beat, False), ("Hover", 30, hover, True)]
for name, n, fn, loop in ACTIONS:
    dlib.write_action(arm, name, n, fn, loop=loop, paired=PAIRED, loc_bones=("Body",))
    print(f"action {name}: {n} frames ({n / 30:.2f}s) loop={loop}")
arm.animation_data.action = bpy.data.actions["Glide"]
bpy.context.scene.frame_start = 0
bpy.context.scene.frame_end = 105

if "--save" in (sys.argv if 'sys' in dir() else []):
    bpy.ops.wm.save_mainfile()
