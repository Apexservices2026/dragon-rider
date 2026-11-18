"""Eevee preview renders of the Viking prop kit (run after build_props.py).

  blender.exe -b --factory-startup --python tools/blender/world/render_previews.py [-- shot ...]

Shots: fleet (3 longships from 80 m, golden hour), village (low aerial vignette),
prow (close-up of dragon prow + shields). Output: Saved/Generated/World/Previews/*.png
The water, sky and ground here are preview-only set dressing (not part of the kit).
"""
import math
import os
import sys
import time

import bpy
from mathutils import Euler, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(REPO, "Game", "DragonRider", "Saved", "Generated", "World")
PREV = os.path.join(OUT, "Previews")
os.makedirs(PREV, exist_ok=True)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SHOTS = argv or ["fleet", "village", "prow"]
RES = (1600, 900)

bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, "VikingKit.blend"))
scene = bpy.context.scene
vl = bpy.context.view_layer
KIT = [c for c in bpy.data.collections]
for lc in vl.layer_collection.children:
    lc.exclude = True

# beached / moored hull without sail and oars
bare = bpy.data.collections.new("Longship_Bare")
bare.objects.link(bpy.data.objects["SM_Longship_ClanA"])
bpy.context.scene.collection.children.link(bare)
vl.layer_collection.children["Longship_Bare"].exclude = True

SET = bpy.data.collections.new("PreviewSet")
scene.collection.children.link(SET)


def inst(coll, loc, rz=0.0, s=1.0, rx=0.0, ry=0.0, group=None):
    e = bpy.data.objects.new(f"I_{coll}", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = bpy.data.collections[coll]
    e.location = loc
    e.rotation_euler = (math.radians(rx), math.radians(ry), math.radians(rz))
    e.scale = (s, s, s)
    (group or SET).objects.link(e)
    return e


# --------------------------------------------------------------------------- render settings
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = RES
scene.render.resolution_percentage = int(os.environ.get("PCT", "100"))
ee = scene.eevee
ee.taa_render_samples = 48
for attr, val in (("use_raytracing", True), ("use_shadows", True), ("shadow_ray_count", 2), ("shadow_step_count", 8),
                  ("use_volumetric_shadows", True), ("volumetric_tile_size", "8"), ("volumetric_end", 2500.0)):
    try:
        setattr(ee, attr, val)
    except Exception as ex:  # noqa: BLE001
        print("eevee attr", attr, ex)
try:
    ee.ray_tracing_options.resolution_scale = "2"
except Exception:  # noqa: BLE001
    pass
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass
scene.view_settings.exposure = 0.0
scene.render.image_settings.file_format = "PNG"

# --------------------------------------------------------------------------- world + sun
SUN_ELEV = 6.0
SUN_AZ = 215.0   # degrees, direction the light comes FROM measured from +X toward +Y
world = bpy.data.worlds.new("GoldenHour")
scene.world = world
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
sky = nt.nodes.new("ShaderNodeTexSky")
sky.sky_type = "MULTIPLE_SCATTERING"
sky.sun_elevation = math.radians(SUN_ELEV)
sky.sun_rotation = math.radians(SUN_AZ - 90)
sky.sun_disc = True
sky.air_density = 1.2
sky.aerosol_density = 2.0
bg = nt.nodes.new("ShaderNodeBackground")
bg.inputs["Strength"].default_value = 0.16
wo = nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(sky.outputs[0], bg.inputs[0])
nt.links.new(bg.outputs[0], wo.inputs["Surface"])

sun_d = bpy.data.lights.new("Sun", "SUN")
sun_d.energy = 5.0
sun_d.color = (1.0, 0.60, 0.33)
sun_d.angle = math.radians(0.8)
sun = bpy.data.objects.new("Sun", sun_d)
SET.objects.link(sun)
az = math.radians(SUN_AZ)
el = math.radians(SUN_ELEV)
ldir = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))  # toward the sun
sun.rotation_euler = (-ldir).to_track_quat("-Z", "Y").to_euler()

# --------------------------------------------------------------------------- water
def water_material():
    m = bpy.data.materials.new("PreviewWater")
    m.use_nodes = True
    t = m.node_tree
    bs = t.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (0.006, 0.02, 0.026, 1)
    bs.inputs["Roughness"].default_value = 0.07
    bs.inputs["IOR"].default_value = 1.33
    tc = t.nodes.new("ShaderNodeTexCoord")
    mp = t.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1, 1.6, 1)
    t.links.new(tc.outputs["Object"], mp.inputs[0])
    n1 = t.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 0.35
    n1.inputs["Detail"].default_value = 6
    n1.inputs["Roughness"].default_value = 0.6
    t.links.new(mp.outputs[0], n1.inputs["Vector"])
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.4
    t.links.new(n1.outputs["Fac"], bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return m


def plane(name, size, z, mat, sub=0):
    me = bpy.data.meshes.new(name)
    h = size / 2
    me.from_pydata([(-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z)], [], [(0, 1, 2, 3)])
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    SET.objects.link(ob)
    return ob


WATER = plane("Water", 8000, 0.0, water_material())


# --------------------------------------------------------------------------- shore terrain (village shot)
def ground_z(x, y):
    shore = -8.0
    z = (y - shore) * 0.075
    if y > 24:
        z += 0.0035 * (y - 24) ** 2
    z += 0.25 * math.sin(x * 0.07) * math.sin(y * 0.05 + 1) + 0.12 * math.sin(x * 0.21 + y * 0.13)
    z += 0.002 * x * x * 0.08
    if y < shore:
        z = max(z, -9.0)
    return z


def ground_material():
    m = bpy.data.materials.new("PreviewGround")
    m.use_nodes = True
    t = m.node_tree
    bs = t.nodes["Principled BSDF"]
    tc = t.nodes.new("ShaderNodeTexCoord")
    mp = t.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.11, 0.11, 0.11)
    mp.inputs["Rotation"].default_value = (0, 0, 0.5)
    t.links.new(tc.outputs["Object"], mp.inputs[0])
    img = t.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images["T_Turf_BC"]
    t.links.new(mp.outputs[0], img.inputs[0])
    nim = t.nodes.new("ShaderNodeTexImage")
    nim.image = bpy.data.images["T_Turf_N"]
    t.links.new(mp.outputs[0], nim.inputs[0])
    nm = t.nodes.new("ShaderNodeNormalMap")
    t.links.new(nim.outputs[0], nm.inputs["Color"])
    t.links.new(nm.outputs[0], bs.inputs["Normal"])
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(tc.outputs["Object"], sep.inputs[0])
    mr = t.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.35
    mr.inputs["From Max"].default_value = 1.1
    t.links.new(sep.outputs["Z"], mr.inputs["Value"])
    noise = t.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    t.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    sand = t.nodes.new("ShaderNodeMix")
    sand.data_type = "RGBA"
    sand.inputs["A"].default_value = (0.28, 0.24, 0.18, 1)
    sand.inputs["B"].default_value = (0.16, 0.15, 0.13, 1)
    t.links.new(noise.outputs["Fac"], sand.inputs["Factor"])
    mixc = t.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    t.links.new(mr.outputs[0], mixc.inputs["Factor"])
    t.links.new(sand.outputs["Result"], mixc.inputs["A"])
    gn = t.nodes.new("ShaderNodeTexNoise")
    gn.inputs["Scale"].default_value = 0.6
    gn.inputs["Detail"].default_value = 8
    t.links.new(tc.outputs["Object"], gn.inputs["Vector"])
    gr = t.nodes.new("ShaderNodeValToRGB")
    gr.color_ramp.elements[0].color = (0.06, 0.10, 0.03, 1)
    gr.color_ramp.elements[1].color = (0.20, 0.22, 0.08, 1)
    t.links.new(gn.outputs["Fac"], gr.inputs[0])
    t.links.new(gr.outputs["Color"], mixc.inputs["B"])
    big = t.nodes.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 0.035
    big.inputs["Detail"].default_value = 4
    t.links.new(tc.outputs["Object"], big.inputs["Vector"])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.55, 0.6, 0.45, 1)
    ramp.color_ramp.elements[1].color = (1.25, 1.1, 0.8, 1)
    t.links.new(big.outputs["Fac"], ramp.inputs[0])
    mul = t.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    t.links.new(mixc.outputs["Result"], mul.inputs["A"])
    t.links.new(ramp.outputs["Color"], mul.inputs["B"])
    t.links.new(mul.outputs["Result"], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.92
    return m


def build_ground(group):
    nx, ny = 180, 130
    x0, x1, y0, y1 = -180, 180, -40, 220
    verts, faces = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            y = y0 + (y1 - y0) * j / ny
            verts.append((x, y, ground_z(x, y)))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new("Ground")
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("use_smooth", [True] * len(faces))
    me.materials.append(ground_material())
    ob = bpy.data.objects.new("Ground", me)
    group.objects.link(ob)


def camera(name, loc, target, lens=35):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_end = 6000
    cam = bpy.data.objects.new(name, cd)
    SET.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return cam


def group(name):
    c = bpy.data.collections.new(name)
    SET.children.link(c)
    return c


# --------------------------------------------------------------------------- shots
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import kit_textures as KT  # noqa: E402


def wake_material():
    n = 512
    foam = KT.fnoise(n, beta=1.0, fmin=6, fmax=200, seed=91)
    u = (np.arange(n)[None, :] + 0.5) / n * np.ones((n, 1))      # across, 0..1 -> y -30..30
    v = (np.arange(n)[:, None] + 0.5) / n * np.ones((1, n))      # along, 0 bow .. 1 far astern
    y = (u - 0.5) * 60.0
    d = v * 92.0
    arm = np.exp(-((np.abs(y) - 0.36 * d - 2.6) / (0.8 + 0.06 * d)) ** 2)
    wash = np.exp(-(y / (2.4 + 0.07 * np.maximum(d - 22, 0))) ** 2) * KT.sstep(18, 26, d)
    arm = np.exp(-((np.abs(y) - 0.34 * d - 2.4) / (0.35 + 0.03 * d)) ** 2) * KT.sstep(0, 3, d)
    wash = np.exp(-(y / (1.6 + 0.04 * np.maximum(d - 22, 0))) ** 2) * KT.sstep(19, 25, d)
    a = np.clip((arm * 0.6 + wash * 0.7) * KT.sstep(-0.3, 1.6, foam), 0, 1) * np.exp(-d / 30.0)
    rgba = np.ones((n, n, 4), dtype=np.float32)
    rgba[..., 3] = a
    img = bpy.data.images.new("WakeAlpha", n, n, alpha=True)
    img.pixels.foreach_set(rgba.ravel())
    img.pack()
    m = bpy.data.materials.new("PreviewWake")
    m.use_nodes = True
    t = m.node_tree
    bs = t.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (0.75, 0.78, 0.78, 1)
    bs.inputs["Roughness"].default_value = 0.5
    it = t.nodes.new("ShaderNodeTexImage")
    it.image = img
    it.extension = "CLIP"
    t.links.new(it.outputs["Alpha"], bs.inputs["Alpha"])
    m.surface_render_method = "BLENDED"
    m.use_transparency_overlap = False
    return m


WAKE_MAT = wake_material()


def wake(parent_loc, rz, group):
    me = bpy.data.meshes.new("Wake")
    me.from_pydata([(12, 30, 0), (12, -30, 0), (-80, -30, 0), (-80, 30, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new()
    for li, (uu, vv) in enumerate([(1, 0), (0, 0), (0, 1), (1, 1)]):
        uv.data[li].uv = (uu, vv)
    me.materials.append(WAKE_MAT)
    ob = bpy.data.objects.new("Wake", me)
    ob.location = (parent_loc[0], parent_loc[1], 0.03)
    ob.rotation_euler = (0, 0, math.radians(rz))
    ob.visible_shadow = False
    group.objects.link(ob)


G_FLEET = group("G_Fleet")
FX = 3000.0
for clan, (x, y, rz) in (("ClanA", (0, 0, 4)), ("ClanA", (-34, 24, -3)), ("ClanB", (-28, -22, 8))):
    inst(f"Longship_{clan}", (FX + x, y, 0), rz=rz, group=G_FLEET)
    wake((FX + x, y), rz, G_FLEET)

G_VIL = group("G_Village")
build_ground(G_VIL)


def gz(x, y):
    return ground_z(x, y)


inst("Longhouse", (0, 26, gz(0, 26) - 0.15), rz=2, group=G_VIL)
for (x, y, r, s) in ((-17, 14, 22, 1.0), (16, 13, -16, 0.9), (-14, 38, 84, 1.1)):
    inst("Hut", (x, y, gz(x, y) - 0.1), rz=r, s=s, group=G_VIL)
inst("Storehouse", (10, 39, gz(10, 39) - 0.1), rz=-8, group=G_VIL)
inst("Smithy", (22, 29, gz(22, 29) - 0.1), rz=-100, group=G_VIL)
inst("WoodPile", (24.5, 24.5, gz(24.5, 24.5)), rz=-10, group=G_VIL)
inst("Watchtower", (-27, 33, gz(-27, 33) - 0.2), rz=12, group=G_VIL)
# pier out to sea along -Y
for k, y in enumerate((4.0, -1.0, -6.0, -11.0, -16.0)):
    inst("PierSection", (4, y, 0), rz=-90, group=G_VIL)
inst("PierEnd", (4, -21.0, 0), rz=-90, group=G_VIL)
inst("Longship_Bare", (11.5, -19, 0.0), rz=-92, group=G_VIL)
inst("Longship_Bare", (-21, -0.5, 1.45), rz=96, ry=-4.3, group=G_VIL)
for (x, y, r) in ((3.2, -20.5, 0), (4.6, -21.6, 30), (3.5, -19.6, 60)):
    inst("Barrel", (x, y, 1.0), rz=r, group=G_VIL)
inst("Crate", (4.9, -19.2, 1.0), rz=12, group=G_VIL)
inst("Crate", (4.9, -19.2, 1.62), rz=-5, s=0.9, group=G_VIL)
inst("Barrel", (3.0, 30.5, gz(3, 30.5)), group=G_VIL)
inst("Crate", (-3.5, 30.8, gz(-3.5, 30.8)), rz=40, group=G_VIL)
inst("Banner_ClanA", (6.0, -22.8, 1.0), rz=-90, group=G_VIL)
inst("Banner_ClanA", (1.6, 30.6, gz(1.6, 30.6)), rz=0, group=G_VIL)
# palisade ring around the inland side, gate on the axis
C = Vector((0, 24))
R = 38.0
step = 2 * math.degrees(math.asin(3.0 / R))
nseg = 18
for k in range(nseg):
    a = 90 + (k - nseg // 2) * step
    p = C + Vector((math.cos(math.radians(a)), math.sin(math.radians(a)))) * R
    inst("PalisadeGate" if k == nseg // 2 else "PalisadeWall", (p.x, p.y, gz(p.x, p.y)), rz=a - 90, group=G_VIL)

G_PROW = group("G_Prow")
PX = -3000.0
inst("Longship_ClanA", (PX, 0, 0), rz=0, group=G_PROW)


def show_only(g):
    for c in SET.children:
        c.hide_render = c is not g


TIMES = {}


def render(name, cam, g, exposure=0.0, samples=48):
    show_only(g)
    scene.camera = cam
    scene.view_settings.exposure = exposure
    scene.eevee.taa_render_samples = samples
    scene.render.filepath = os.path.join(PREV, f"preview_{name}.png")
    t = time.time()
    bpy.ops.render.render(write_still=True)
    TIMES[name] = round(time.time() - t, 1)
    print(f"RENDER {name} {TIMES[name]}s -> {scene.render.filepath}")


if "fleet" in SHOTS:
    cam = camera("CamFleet", (FX - 60, -66, 80), (FX - 16, -9, 0), lens=40)
    render("fleet", cam, G_FLEET)
if "village" in SHOTS:
    cam = camera("CamVillage", (42, -58, 30), (-2, 12, 2), lens=30)
    render("village", cam, G_VIL)
if "prow" in SHOTS:
    cam = camera("CamProw", (PX + 16.5, -6.8, 3.4), (PX + 10.2, -1.3, 4.0), lens=32)
    render("prow", cam, G_PROW)
if "hull" in SHOTS:
    cam = camera("CamHull", (PX + 3, -9, 1.6), (PX - 1, -2.4, 0.7), lens=35)
    render("hull", cam, G_PROW)
if "lineup" in SHOTS:
    G_LINE = group("G_Line")
    x = 0.0
    for name, w in (("Hut", 10), ("Storehouse", 7), ("Smithy", 9), ("Watchtower", 7), ("PalisadeWall", 8),
                    ("PalisadeGate", 8), ("PierEnd", 7), ("Barrel", 2), ("Crate", 2), ("WoodPile", 3.5),
                    ("Banner_ClanB", 2)):
        x += w / 2
        inst(name, (-6000 + x, 0, 0.0), rz=-25 if name in ("Hut", "Storehouse", "Smithy") else 0, group=G_LINE)
        x += w / 2
    gp = plane("LineGround", 200, 0.01, bpy.data.materials["PreviewGround"])
    gp.location = (-6000, 0, 0)
    G_LINE.objects.link(gp)
    SET.objects.unlink(gp)
    cam = camera("CamLine", (-6000 + 33, -58, 16), (-6000 + 33, 0, 2.5), lens=40)
    render("lineup", cam, G_LINE)
print("TIMES", TIMES)
