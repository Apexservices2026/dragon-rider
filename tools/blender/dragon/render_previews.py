"""Eevee preview stills of the dragon (+ rider) in their actions.

Run:  blender -b --factory-startup --python-exit-code 1 -P tools/blender/dragon/render_previews.py -- [shot ...] [--res 1600]
Loads Saved/Generated/Dragon/Dragon.blend (+ Rider.blend if present, attached at the Saddle
bone), adds a procedural sky + sun, renders PNGs to Saved/Generated/Dragon/Previews/.
No outside assets.
"""
import sys
import os
import math
import time
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlib  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RES = int(argv[argv.index("--res") + 1]) if "--res" in argv else 1600
shots_req = [a for a in argv if not a.startswith("--") and not a.isdigit()]
PREV = os.path.join(dlib.OUT_DIR, "Previews")
os.makedirs(PREV, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=os.path.join(dlib.OUT_DIR, "Dragon.blend"))
sc = bpy.context.scene
arm = bpy.data.objects["DragonRig"]

rider_arm = None
rider_blend = os.path.join(dlib.OUT_DIR, "Rider.blend")
if os.path.exists(rider_blend):
    with bpy.data.libraries.load(rider_blend, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
        dst.actions = [n for n in src.actions if n.startswith("Rider")]
    for o in dst.objects:
        if o is not None and o.name not in sc.collection.objects:
            sc.collection.objects.link(o)
    rider_arm = bpy.data.objects.get("RiderRig")
    if rider_arm:
        rider_arm.parent = arm
        rider_arm.parent_type = 'BONE'
        rider_arm.parent_bone = "Saddle"
        # bone parenting puts the child at the bone TAIL; offset back to the head (seat point)
        b = arm.data.bones["Saddle"]
        rider_arm.matrix_parent_inverse.identity()
        rider_arm.location = (0, -b.length, 0)
        rider_arm.rotation_euler = (0, 0, 0)
        # Saddle bone points +Z; local Y = world Z.  Rotate rider so its +X/+Z match the dragon's
        rider_arm.rotation_mode = 'QUATERNION'
        bm = b.matrix_local.to_3x3()
        rider_arm.rotation_quaternion = bm.inverted().to_quaternion()
        if rider_arm.animation_data and "RiderIdle" in bpy.data.actions:
            act = bpy.data.actions["RiderIdle"]
            rider_arm.animation_data.action = act
            if rider_arm.animation_data.action_slot is None and len(act.slots):
                rider_arm.animation_data.action_slot = act.slots[0]

# ------------------------------------------------------------------ world / light
world = bpy.data.worlds.new("Sky")
sc.world = world
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
sky = nt.nodes.new("ShaderNodeTexSky")
sky.sky_type = 'MULTIPLE_SCATTERING'
sky.sun_elevation = math.radians(14)
sky.sun_rotation = math.radians(200)
sky.altitude = 1500
sky.air_density = 1.2
sky.aerosol_density = 1.6
bg = nt.nodes.new("ShaderNodeBackground")
bg.inputs['Strength'].default_value = 0.25
out = nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(sky.outputs[0], bg.inputs[0])
nt.links.new(bg.outputs[0], out.inputs[0])

sun_d = bpy.data.lights.new("Sun", 'SUN')
sun_d.energy = 4.0
sun_d.color = (1.0, 0.86, 0.70)
sun_d.angle = math.radians(1.5)
sun = bpy.data.objects.new("Sun", sun_d)
sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(62), 0, math.radians(200 + 90))
rim_d = bpy.data.lights.new("Rim", 'SUN')
rim_d.energy = 1.6
rim_d.color = (0.55, 0.65, 1.0)
rim = bpy.data.objects.new("Rim", rim_d)
sc.collection.objects.link(rim)
rim.rotation_euler = (math.radians(110), 0, math.radians(30))

sc.render.engine = 'BLENDER_EEVEE'
try:
    sc.eevee.taa_render_samples = 48
    sc.eevee.use_shadows = True
    sc.eevee.use_raytracing = False
except Exception:
    pass
sc.render.resolution_x = RES
sc.render.resolution_y = int(RES * 9 / 16)
sc.render.film_transparent = False
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Punchy'
sc.view_settings.exposure = 0.2

cam_d = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
cam_d.clip_end = 2000


def look(loc, target, lens=50, roll=0.0):
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    q = d.to_track_quat('-Z', 'Y')
    cam.rotation_mode = 'QUATERNION'
    cam.rotation_quaternion = q
    if roll:
        from mathutils import Quaternion
        cam.rotation_quaternion = q @ Quaternion((0, 0, 1), roll)
    cam_d.lens = lens


def pose(action, frame):
    act = bpy.data.actions[action]
    arm.animation_data.action = act
    if arm.animation_data.action_slot is None and len(act.slots):
        arm.animation_data.action_slot = act.slots[0]
    sc.frame_set(frame)


SHOTS = {
    "flap_34front": dict(action="Flap", frame=7, cam=((13.0, -12.5, 4.5), (0.2, 0, 0.8), 32)),
    "glide_side": dict(action="Glide", frame=20, cam=((0.3, -26.0, 2.2), (-0.3, 0, 0.7), 40)),
    "dive_top": dict(action="DiveTuck", frame=10, cam=((0.0, -0.001, 23.0), (0.0, 0.0, 0.0), 40)),
    "head_close": dict(action="Glide", frame=0, cam=((7.0, -2.6, 2.1), (4.85, 0, 1.5), 50)),
    "rider_close": dict(action="Glide", frame=30, cam=("seat", (2.3, -2.6, 0.75), (0.1, 0, 0.45), 40)),
    "rider_rear": dict(action="Glide", frame=30, cam=("seat", (-3.2, -2.4, 1.4), (0.1, 0, 0.4), 35)),
    "hero": dict(action="Flap", frame=0, cam=((7.4, -6.2, -0.9), (0.6, 0.4, 1.5), 24)),
    "dive_side": dict(action="DiveTuck", frame=10, cam=((6.0, -16.0, 6.0), (0.0, 0, 0.3), 40)),
    "dive_rear": dict(action="DiveTuck", frame=10, cam=((-7.0, -5.0, 4.0), (0.5, 0, 0.5), 35)),
    "hover_front": dict(action="Hover", frame=8, cam=((16.0, -6.0, 1.0), (0.0, 0, 1.0), 32)),
    "beat_34rear": dict(action="WingBeatStrong", frame=12, cam=((-12.0, -11.0, 5.0), (0.0, 0, 0.8), 32)),
}
names = shots_req or list(SHOTS)
times = {}
for n in names:
    s = SHOTS[n]
    pose(s["action"], s["frame"])
    c = s["cam"]
    if c[0] == "seat":
        seat = arm.data.bones["Saddle"].head_local
        c = (seat + Vector(c[1]), seat + Vector(c[2]), c[3])
    look(c[0], c[1], c[2], c[3] if len(c) > 3 else 0.0)
    if n == "hero":
        sun.rotation_euler = (math.radians(74), 0, math.radians(-130))
        sun_d.energy, rim_d.energy = 5.0, 2.2
        rim.rotation_euler = (math.radians(50), 0, math.radians(60))
        sky.sun_elevation = math.radians(6)
        sky.sun_rotation = math.radians(150)
        sc.view_settings.exposure = 0.35
    else:
        sun.rotation_euler = (math.radians(55), 0, math.radians(-30))
        sun_d.energy, rim_d.energy = 4.0, 1.6
        rim.rotation_euler = (math.radians(110), 0, math.radians(30))
        sky.sun_elevation = math.radians(14)
        sky.sun_rotation = math.radians(200)
        sc.view_settings.exposure = 0.2
    sc.render.filepath = os.path.join(PREV, f"{n}.png")
    t = time.time()
    bpy.ops.render.render(write_still=True)
    times[n] = time.time() - t
    print(f"RENDER {n}: {times[n]:.1f}s -> {sc.render.filepath}", flush=True)
print("RENDER TOTAL %.1fs" % sum(times.values()))
