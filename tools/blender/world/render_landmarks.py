"""Eevee previews of the archipelago landmarks (run after build_landmarks.py).

  blender.exe -b --factory-startup --python tools/blender/world/render_landmarks.py [-- stronghold rune lair waterfall]

Ground, sea and sky here are preview-only set dressing. Output: Saved/Generated/World/Previews/landmark_*.png
"""
import math
import os
import sys
import time

import bpy
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(REPO, "Game", "DragonRider", "Saved", "Generated", "World")
PREV = os.path.join(OUT, "Previews")
os.makedirs(PREV, exist_ok=True)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SHOTS = argv or ["stronghold", "rune", "lair", "waterfall"]

bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, "Landmarks.blend"))
scene = bpy.context.scene
vl = bpy.context.view_layer
with bpy.data.libraries.load(os.path.join(OUT, "VikingKit.blend"), link=False) as (src, dst):
    dst.collections = [c for c in src.collections if c in ("Hut", "Watchtower", "Banner_ClanA", "Barrel", "Storehouse",
                                                            "Longship_ClanA", "WoodPile", "Crate")]
for lc in vl.layer_collection.children:
    lc.exclude = True
SET = bpy.data.collections.new("PreviewSet")
scene.collection.children.link(SET)


def group(name):
    c = bpy.data.collections.new(name)
    SET.children.link(c)
    return c


def inst(coll, loc, rz=0.0, s=1.0, g=None, sv=None):
    e = bpy.data.objects.new(f"I_{coll}", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = bpy.data.collections[coll]
    e.location = loc
    e.rotation_euler = (0, 0, math.radians(rz))
    e.scale = sv or (s, s, s)
    (g or SET).objects.link(e)
    return e


scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1600, 900
scene.render.resolution_percentage = int(os.environ.get("PCT", "100"))
scene.eevee.taa_render_samples = 48
for attr, val in (("use_raytracing", True), ("use_shadows", True)):
    try:
        setattr(scene.eevee, attr, val)
    except Exception:  # noqa: BLE001
        pass
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass

world = bpy.data.worlds.new("Sky")
scene.world = world
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
SKY = nt.nodes.new("ShaderNodeTexSky")
SKY.sky_type = "MULTIPLE_SCATTERING"
BG = nt.nodes.new("ShaderNodeBackground")
WO = nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(SKY.outputs[0], BG.inputs[0])
nt.links.new(BG.outputs[0], WO.inputs["Surface"])
SUN_D = bpy.data.lights.new("Sun", "SUN")
SUN_D.angle = math.radians(0.8)
SUN = bpy.data.objects.new("Sun", SUN_D)
SET.objects.link(SUN)


def light(elev, az, energy, color, sky_strength):
    SKY.sun_elevation = math.radians(elev)
    SKY.sun_rotation = math.radians(az - 90)
    BG.inputs["Strength"].default_value = sky_strength
    SUN_D.energy = energy
    SUN_D.color = color
    a, e = math.radians(az), math.radians(elev)
    d = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
    SUN.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def simple_mat(name, base, rough=0.9, noise_scale=0.0, base2=None, emit=None, emit_strength=0.0, bump=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    bs = t.nodes["Principled BSDF"]
    bs.inputs["Roughness"].default_value = rough
    if base2:
        tc = t.nodes.new("ShaderNodeTexCoord")
        nz = t.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = noise_scale
        nz.inputs["Detail"].default_value = 8
        t.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        ramp = t.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = base + (1,)
        ramp.color_ramp.elements[1].color = base2 + (1,)
        t.links.new(nz.outputs["Fac"], ramp.inputs[0])
        t.links.new(ramp.outputs[0], bs.inputs["Base Color"])
        if bump:
            b = t.nodes.new("ShaderNodeBump")
            b.inputs["Strength"].default_value = bump
            t.links.new(nz.outputs["Fac"], b.inputs["Height"])
            t.links.new(b.outputs[0], bs.inputs["Normal"])
    else:
        bs.inputs["Base Color"].default_value = base + (1,)
    if emit:
        bs.inputs["Emission Color"].default_value = emit + (1,)
        bs.inputs["Emission Strength"].default_value = emit_strength
    return m


def water_mat():
    m = simple_mat("PWater", (0.006, 0.02, 0.026), rough=0.06)
    t = m.node_tree
    bs = t.nodes["Principled BSDF"]
    tc = t.nodes.new("ShaderNodeTexCoord")
    nz = t.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.4
    nz.inputs["Detail"].default_value = 6
    t.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    b = t.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = 0.2
    t.links.new(nz.outputs["Fac"], b.inputs["Height"])
    t.links.new(b.outputs[0], bs.inputs["Normal"])
    return m


def grid(name, cx, cy, size, n, hfn, mat, g):
    vs, fs = [], []
    for j in range(n + 1):
        for i in range(n + 1):
            x = cx - size / 2 + size * i / n
            y = cy - size / 2 + size * j / n
            vs.append((x, y, hfn(x - cx, y - cy)))
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            fs.append((a, a + 1, a + n + 2, a + n + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.polygons.foreach_set("use_smooth", [True] * len(fs))
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    g.objects.link(ob)
    return ob


def plane(name, size, loc, mat, g):
    h = size / 2
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    g.objects.link(ob)
    return ob


def camera(name, loc, target, lens):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_end = 5000
    cam = bpy.data.objects.new(name, cd)
    SET.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return cam


def fbm(x, y, s=0.02, o=0.0):
    return noise.fractal(Vector((x * s + o, y * s - o, 0.3)), 0.8, 2.0, 5)


GROUPS = {}
WATER = water_mat()

# ---------------------------------------------------------------- 1. stronghold on a sea cliff
G = GROUPS["stronghold"] = group("G_Strong")
PLAT = 40.0


def cliff_h(x, y):
    base = PLAT + 1.5 * fbm(x, y, 0.03)
    edge = 52 + 6 * fbm(x, y, 0.02, 5)
    if x > edge:
        base = max(-6.0, base - (x - edge) * 7.0)
    return base - 0.0005 * (x * x + y * y) * (x < edge) * 0.5


grid("GStrong", 0, 0, 360, 220, cliff_h, simple_mat("PGrass", (0.05, 0.085, 0.025), 0.95, 0.08, (0.15, 0.17, 0.06), bump=0.3), G)
plane("SeaA", 3000, (0, 0, 0), WATER, G)
inst("MeadHall", (0, 0, PLAT - 0.2), rz=180, g=G)
R = 30.6
step = 15.0
for k in range(24):
    a = k * step
    if k in (12,):
        continue
    p = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)))) * R
    inst("FortWallCurve15", (p.x, p.y, cliff_h(p.x, p.y) - 0.3), rz=a - 90, g=G)
gp = Vector((-R, 0))
inst("Gatehouse", (gp.x - 1.0, 0, cliff_h(gp.x, 0) - 0.2), rz=180, g=G)
for (x, y, r) in ((-15, 18, 70), (14, 19, -60), (-14, -19, 110)):
    inst("Hut", (x, y, cliff_h(x, y) - 0.1), rz=r, g=G)
inst("Storehouse", (17, -17, cliff_h(17, -17) - 0.1), rz=30, g=G)
inst("BeaconTower", (52, -30, cliff_h(52, -30) - 0.3), g=G)
inst("Banner_ClanA", (-25, 4, PLAT), g=G)
inst("Banner_ClanA", (-25, -4, PLAT), g=G)
inst("Longship_ClanA", (95, 40, 0), rz=200, g=G)

# ---------------------------------------------------------------- 2. rune circle on the glacier isle
G = GROUPS["rune"] = group("G_Rune")
RX = 3000.0


def snow_h(x, y):
    r = math.hypot(x, y)
    return 0.6 * fbm(x, y, 0.04) + max(0.0, r - 40) ** 1.5 * 0.08


grid("GSnow", RX, 0, 400, 160, snow_h, simple_mat("PSnow", (0.62, 0.68, 0.76), 0.6, 0.15, (0.86, 0.9, 0.96), bump=0.2), G)
inst("RuneCircle", (RX, 0, 0), g=G)
inst("IceShrine", (RX + 17, 0, 0), g=G)
for (x, y, n, s, r) in ((-14, 9, "FrostBoulder_A", 1.0, 20), (-11, -13, "FrostBoulder_B", 1.3, 80), (12, -14, "FrostBoulder_C", 1.0, 0),
                        (6, 15, "FrostBoulder_B", 0.8, 140), (-30, 22, "FrostBoulder_C", 2.5, 10), (28, 26, "FrostBoulder_A", 3.0, 50),
                        (35, -24, "FrostBoulder_C", 2.2, 90), (-4, -20, "FrostBoulder_A", 0.6, 30)):
    inst(n, (RX + x, y, snow_h(x, y) - 0.2), rz=r, s=s, g=G)

# ---------------------------------------------------------------- 3. dragon lair in the caldera
G = GROUPS["lair"] = group("G_Lair")
LX = -3000.0


def cal_h(x, y):
    r = math.hypot(x, y)
    h = 0.5 * fbm(x, y, 0.06) + (max(0.0, r - 45) ** 1.3) * 0.9
    d = math.hypot(x + 10, y + 30)
    if d < 12:
        h -= 1.4 * (1 - (d / 12) ** 2)
    return h


grid("GAsh", LX, 0, 300, 200, cal_h, simple_mat("PAsh", (0.035, 0.03, 0.028), 0.95, 0.25, (0.11, 0.095, 0.085), bump=0.4), G)
inst("DragonNest", (LX, 0, -0.2), g=G)
inst("DragonSkull", (LX - 15, 9, 0), rz=-30, g=G)
inst("DragonRibs", (LX + 15, 14, 0), rz=20, g=G)
inst("ObsidianSpires_A", (LX - 20, -15, -0.5), rz=10, g=G)
inst("ObsidianSpires_B", (LX + 19, -4, -0.3), rz=80, g=G)
inst("ObsidianSpires_B", (LX - 6, 24, -0.3), rz=200, s=1.3, g=G)
for k in range(7):
    a = 2 * math.pi * k / 7 + 0.4
    inst("EmberCrystals", (LX + 12.5 * math.cos(a), 12.5 * math.sin(a), 0), rz=k * 47, s=0.8 + 0.1 * (k % 3), g=G)
for k in range(9):
    a = 2 * math.pi * k / 9 + 0.1
    r = 18 + 6 * (k % 3)
    inst(f"LavaRock_{'ABC'[k % 3]}", (LX + r * math.cos(a), r * math.sin(a), -0.3), rz=k * 33, g=G)

# ---------------------------------------------------------------- 4. waterfall gorge
G = GROUPS["waterfall"] = group("G_Falls")
WY = 3000.0
sheet = bpy.data.objects["SM_WaterfallSheet"]
lip = bpy.data.objects["SM_FallsLip"]
import json  # noqa: E402
man = json.load(open(os.path.join(OUT, "props_manifest.json")))
ent = [p for p in man["landmarks"]["props"] if p["name"] == "WaterfallSheet"][0]["attach_points"]
top = Vector(ent["top_edge_local_m"])
crest = Vector(ent["FallsLip_crest_m"])
S0 = Vector((0, WY, 0))
inst("WaterfallSheet", S0, g=G)
lip_pos = S0 + top - crest
inst("FallsLip", lip_pos, g=G)
for sy, sc in ((-1, (1.3, 1.0, 4.0)), (1, (1.2, 1.1, 4.3))):
    inst("FallsLip", (lip_pos.x - 2, WY + sy * 15, -4), rz=90 * sy, sv=sc, g=G)
    inst("FallsLip", (lip_pos.x + 14, WY + sy * 19, -4), rz=60 * sy, sv=(1.4, 1.0, 3.0), g=G)
inst("PlungeRocks", (6, WY, 0), g=G)
inst("WaterfallFoam", (1.0, WY, 0), g=G)
inst("DriftwoodPile", (22, WY - 7, 0.2), rz=30, g=G)
plane("SeaW", 3000, (0, 0, 0), WATER, G)
PZ = lip_pos.z + 2.5
for k in range(-4, 5):
    if k == 0:
        continue
    inst("FallsLip", (lip_pos.x - 9, WY + k * 11, PZ - 26 + (k % 2) * 3), rz=90 + k * 23, sv=(1.6, 1.4, 4.2), g=G)
inst("FallsLip", (lip_pos.x - 12, WY, PZ - 27), rz=90, sv=(1.4, 1.3, 3.6), g=G)
grid("GForest", 0, WY, 300, 120, lambda x, y: PZ + 2 * fbm(x, y, 0.05) if x < lip_pos.x - 2 else -3.0,
     simple_mat("PForest", (0.03, 0.06, 0.02), 0.95, 0.1, (0.09, 0.12, 0.04), bump=0.3), G)


def show(g):
    for c in SET.children:
        c.hide_render = c is not g


TIMES = {}


def render(name, cam):
    show(GROUPS[name])
    scene.camera = cam
    scene.render.filepath = os.path.join(PREV, f"landmark_{name}.png")
    t = time.time()
    bpy.ops.render.render(write_still=True)
    TIMES[name] = round(time.time() - t, 1)


if "stronghold" in SHOTS:
    light(9, 200, 4.5, (1.0, 0.68, 0.42), 0.2)
    render("stronghold", camera("CStrong", (62, -58, 66), (-4, 2, PLAT + 2), 32))
if "rune" in SHOTS:
    light(7, 150, 4.0, (1.0, 0.8, 0.62), 0.25)
    scene.view_settings.exposure = -0.6
    render("rune", camera("CRune", (RX - 24, -22, 8.5), (RX + 3, 0, 3.0), 30))
scene.view_settings.exposure = 0.0
if "lair" in SHOTS:
    light(5, 230, 3.2, (1.0, 0.45, 0.28), 0.12)
    render("lair", camera("CLair", (LX + 34, -36, 24), (LX, 0, 1.5), 32))
if "waterfall" in SHOTS:
    light(12, 160, 4.0, (1.0, 0.75, 0.5), 0.25)
    render("waterfall", camera("CFalls", (42, WY - 12, 7), (0, WY, 12), 28))
print("TIMES", TIMES)
