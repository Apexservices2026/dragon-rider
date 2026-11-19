"""Build the archipelago level: Landscape islands in a World Partition world, auto landscape material, sky and sea.

Run headless (rebuilds everything under /Game/DragonRider/Archipelago; nothing else is touched):
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>" -AllowCommandletRendering
-AllowCommandletRendering is required: landscape heights are merged from their edit layer on the GPU.
Requires the heightmaps + layout from tools/terrain/gen_archipelago.py (Saved/Generated/Archipelago/) and the
DragonRiderEditor module (UDragonLandscapeLibrary, C++). Runs tools/place_archipelago.py at the end (villages,
fleet), when the world kit has been imported.

Design:
- One Landscape per island (+ small skerry tiles), not one landscape over the whole archipelago: the islands sit
  in ~30 km of open sea, and a single landscape would spend most of its components on flat sea floor.
  Each island has its own resolution (2 m/px, main island 3.5 m/px from the 30 m DEM).
- World Partition: every landscape is split into 8x8-component streaming proxies. They are not spatially loaded
  for now (the whole archipelago is in view from the air); switching bSpatiallyLoaded on + building HLODs is the
  path to more islands later.
- Material: one auto material (height / slope / noise, no painted layers) with per-island material instances.
  Texture parameters (T_*_Albedo / T_*_Normal, UseTextures) take Megascans later.
- Sea: a 60 km water plane at Z=0 (the dragon's plunge plane), plus a far-ocean skirt 400 km across just below
  it (no collision) so the sea runs out to the fogged horizon instead of ending in a white band.
"""
import json
import math
import os
import unreal

ROOT = '/Game/DragonRider/Archipelago'
LEVEL = ROOT + '/Lvl_Archipelago'
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
GEN = os.path.join(PROJECT_DIR, 'Saved', 'Generated', 'Archipelago')
LAYOUT = json.load(open(os.path.join(GEN, 'archipelago.json')))

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty


def log(msg):
    unreal.log('ARCHIPELAGO_BUILD: ' + msg)


# ---------------------------------------------------------------- clean previous build of OUR folder only
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if eal.does_directory_exist(ROOT):
    eal.delete_directory(ROOT)
eal.make_directory(ROOT)


# ---------------------------------------------------------------- material graph helpers
class Graph:
    def __init__(self, mat):
        self.m = mat
        self.n = 0

    def node(self, cls):
        self.n += 1
        return mel.create_material_expression(self.m, cls, -2400 + (self.n // 14) * 260, (self.n % 14) * 110)

    def k(self, v):
        e = self.node(unreal.MaterialExpressionConstant)
        e.set_editor_property('r', v)
        return e

    def k3(self, c):
        e = self.node(unreal.MaterialExpressionConstant3Vector)
        e.set_editor_property('constant', unreal.LinearColor(c[0], c[1], c[2], 1))
        return e

    def p(self, name, v, group='Layers'):
        e = self.node(unreal.MaterialExpressionScalarParameter)
        e.set_editor_property('parameter_name', name)
        e.set_editor_property('default_value', v)
        e.set_editor_property('group', group)
        return e

    def pc(self, name, c, group='Colours'):
        e = self.node(unreal.MaterialExpressionVectorParameter)
        e.set_editor_property('parameter_name', name)
        e.set_editor_property('default_value', unreal.LinearColor(c[0], c[1], c[2], 1))
        e.set_editor_property('group', group)
        return self.mask(e, rgb=True)

    def tex(self, name, path, uv, normal=False):
        e = self.node(unreal.MaterialExpressionTextureSampleParameter2D)
        e.set_editor_property('parameter_name', name)
        e.set_editor_property('group', 'Textures (Megascans)')
        e.set_editor_property('texture', unreal.load_asset(path))
        if normal:
            e.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        mel.connect_material_expressions(uv, '', e, 'UVs')
        return self.mask(e, rgb=True)

    def mask(self, a, rgb=False, r=False, g=False, b=False):
        e = self.node(unreal.MaterialExpressionComponentMask)
        e.set_editor_property('r', rgb or r); e.set_editor_property('g', rgb or g); e.set_editor_property('b', rgb or b)
        e.set_editor_property('a', False)
        mel.connect_material_expressions(a, '', e, '')
        return e

    def op(self, cls, a, b):
        e = self.node(cls)
        mel.connect_material_expressions(a, '', e, 'A')
        mel.connect_material_expressions(b, '', e, 'B')
        return e

    def mul(self, a, b): return self.op(unreal.MaterialExpressionMultiply, a, b)
    def add(self, a, b): return self.op(unreal.MaterialExpressionAdd, a, b)
    def sub(self, a, b): return self.op(unreal.MaterialExpressionSubtract, a, b)
    def div(self, a, b): return self.op(unreal.MaterialExpressionDivide, a, b)

    def sat(self, a):
        e = self.node(unreal.MaterialExpressionSaturate)
        mel.connect_material_expressions(a, '', e, '')
        return e

    def lerp(self, a, b, t):
        e = self.node(unreal.MaterialExpressionLinearInterpolate)
        mel.connect_material_expressions(a, '', e, 'A')
        mel.connect_material_expressions(b, '', e, 'B')
        mel.connect_material_expressions(t, '', e, 'Alpha')
        return e

    def ramp(self, x, lo, hi):
        """saturate((x - lo) / (hi - lo)); lo/hi are expressions."""
        return self.sat(self.div(self.sub(x, lo), self.sub(hi, lo)))

    def noise(self, scale, levels, lo, hi, pos=None):
        e = self.node(unreal.MaterialExpressionNoise)
        e.set_editor_property('scale', scale)
        e.set_editor_property('levels', levels)
        e.set_editor_property('output_min', lo)
        e.set_editor_property('output_max', hi)
        e.set_editor_property('quality', 1)
        if pos is not None:
            mel.connect_material_expressions(pos, '', e, 'Position')
        return e


def new_material(name):
    return tools.create_asset(name, ROOT, unreal.Material, unreal.MaterialFactoryNew())


# ---------------------------------------------------------------- auto landscape material
# Layers by height (cm) / slope (world normal Z): rock on steep ground, grass/moss -> heath on low flats, snow on
# high flat-ish ground, sand on the shore, wet darkening at the waterline; lava glow in a caldera (Ember only).
lm = new_material('M_ArchipelagoLand')
G = Graph(lm)
wp = G.node(unreal.MaterialExpressionWorldPosition)
z = G.mask(wp, b=True)
xy = G.mask(wp, r=True, g=True)
nrm = G.node(unreal.MaterialExpressionVertexNormalWS)
flat = G.mask(nrm, b=True)

macro = G.noise(0.00009, 3, 0.0, 1.0)                 # multi-kilometre colour drift
big = G.noise(0.0006, 4, 0.0, 1.0)
mid = G.noise(0.0035, 3, 0.72, 1.22)
fine = G.noise(0.03, 2, 0.93, 1.06)
streak = G.noise(0.003, 3, 0.55, 1.2, pos=G.mul(wp, G.k3((1.0, 1.0, 0.12))))   # vertical rock banding

use_tex = G.p('UseTextures', 0.0, 'Textures (Megascans)')
def layer_tex(name, tile_cm, proc):
    uv = G.div(xy, G.p(name + 'TileCm', tile_cm, 'Textures (Megascans)'))
    t = G.tex('T_%s_Albedo' % name, '/Engine/EngineResources/WhiteSquareTexture', uv)
    return G.lerp(proc, G.mul(t, G.pc(name + 'TextureTint', (1, 1, 1), 'Textures (Megascans)')), use_tex), uv

# Rock (slope)
rock_a = G.pc('RockColor', (0.055, 0.052, 0.054))
rock_b = G.pc('RockColorWarm', (0.075, 0.062, 0.05))
rock = G.mul(G.mul(G.lerp(rock_a, rock_b, G.sat(G.add(G.mul(big, G.k(1.4)), G.k(-0.3)))), mid), G.mul(fine, streak))
rock = G.mul(rock, G.lerp(G.k(0.8), G.k(1.2), macro))
rock, rock_uv = layer_tex('Rock', 400.0, rock)

# Grass / moss / heath (flat, low)
grass_a = G.pc('GrassColor', (0.042, 0.052, 0.022))
grass_b = G.pc('HeathColor', (0.085, 0.065, 0.035))
grass_top = G.p('GrassTopCm', 60000.0)
grass = G.mul(G.mul(G.lerp(grass_a, grass_b, G.sat(G.add(G.mul(G.sub(big, G.k(0.45)), G.k(2.0)), G.div(z, grass_top)))), fine), mid)
grass = G.mul(grass, G.lerp(G.k(0.75), G.k(1.15), macro))
grass, grass_uv = layer_tex('Grass', 300.0, grass)
grass_flat = G.p('GrassFlatness', 0.80)
grass_mask = G.mul(G.sat(G.mul(G.sub(flat, G.sub(grass_flat, G.mul(G.sub(mid, G.k(1.0)), G.k(0.25)))), G.k(9.0))),
                   G.ramp(z, G.add(grass_top, G.k(2500.0)), G.sub(grass_top, G.k(2500.0))))

# Sand / black sand (shore)
sand_c = G.pc('SandColor', (0.13, 0.11, 0.08))
sand, sand_uv = layer_tex('Sand', 250.0, G.mul(sand_c, fine))
sand_top = G.p('SandTopCm', 250.0)
sand_mask = G.mul(G.ramp(z, G.add(sand_top, G.k(120.0)), G.sub(sand_top, G.k(120.0))), G.sat(G.mul(G.sub(flat, G.k(0.86)), G.k(8.0))))

# Snow (high, flat-ish; everything above the summit line)
snow_c = G.pc('SnowColor', (0.78, 0.81, 0.87))
snow, snow_uv = layer_tex('Snow', 500.0, G.mul(snow_c, fine))
snow_line = G.add(G.p('SnowLineCm', 115000.0), G.mul(big, G.k(-22000.0)))
snow_fade = G.p('SnowFadeCm', 9000.0)
snow_mask = G.mul(G.ramp(z, snow_line, G.add(snow_line, snow_fade)), G.sat(G.mul(G.sub(flat, G.k(0.35)), G.k(2.2))))
snow_mask = G.sat(G.add(snow_mask, G.mul(G.ramp(z, G.add(snow_line, G.k(30000.0)), G.add(snow_line, G.k(45000.0))),
                                         G.sat(G.mul(G.sub(flat, G.k(0.25)), G.k(4.0))))))

col = G.lerp(rock, grass, grass_mask)
col = G.lerp(col, sand, sand_mask)
col = G.lerp(col, snow, snow_mask)
# Wet shore: darken and gloss the band just above and below the waterline.
wet_top = G.p('WetTopCm', 160.0)
wet = G.ramp(z, wet_top, G.k(-50.0))
col = G.lerp(col, G.mul(col, G.k(0.42)), wet)
col = G.lerp(col, G.mul(col, G.k(0.5)), G.ramp(z, G.k(-100.0), G.k(-1500.0)))   # deeper sea floor
mel.connect_material_property(col, '', MP.MP_BASE_COLOR)

rough = G.lerp(G.lerp(G.lerp(G.k(0.92), G.k(0.86), grass_mask), G.k(0.82), sand_mask), G.k(0.55), snow_mask)
rough = G.lerp(rough, G.k(0.28), wet)
rough = G.lerp(rough, G.k(1.0), G.p('RoughnessToOne', 0.75))   # no grazing glare toward the low sun
mel.connect_material_property(rough, '', MP.MP_ROUGHNESS)
# Low specular: at 0.5 sunlit grass glared cream when looking toward the low sun (same as tune_archipelago_material.py).
mel.connect_material_property(G.p('Specular', 0.15), '', MP.MP_SPECULAR)

# Normals (only with textures): blend per-layer normal maps by the same masks.
flatn = G.k3((0.0, 0.0, 1.0))
def nt(name, uv):
    return G.tex('T_%s_Normal' % name, '/Engine/EngineMaterials/FlatNormal', uv, normal=True)
n_col = G.lerp(nt('Rock', rock_uv), nt('Grass', grass_uv), grass_mask)
n_col = G.lerp(n_col, nt('Sand', sand_uv), sand_mask)
n_col = G.lerp(n_col, flatn, snow_mask)
mel.connect_material_property(G.lerp(flatn, n_col, use_tex), '', MP.MP_NORMAL)

# Lava lake (Ember): emissive in a disc around LavaCentre below LavaTopCm.
lava_c = G.pc('LavaCentre', (0.0, 0.0, 0.0), 'Lava')
lava_xy = G.mask(lava_c, r=True, g=True)
dvec = G.sub(xy, lava_xy)
dist = G.node(unreal.MaterialExpressionLength)
mel.connect_material_expressions(dvec, '', dist, '')
lava_in = G.mul(G.ramp(dist, G.p('LavaRadiusCm', 30000.0, 'Lava'), G.sub(G.p('LavaRadiusCm', 30000.0, 'Lava'), G.k(4000.0))),
                G.ramp(z, G.p('LavaTopCm', 0.0, 'Lava'), G.sub(G.p('LavaTopCm', 0.0, 'Lava'), G.k(1500.0))))
lava_n = G.noise(0.00025, 5, 0.0, 1.0)   # ~40 m crust plates (tune_archipelago_material.py does the same in place)
lava_glow = G.mul(G.mul(G.pc('LavaColor', (1.0, 0.28, 0.04), 'Lava'), G.p('LavaGlow', 0.0, 'Lava')),
                  G.mul(lava_in, G.mul(G.sat(G.add(G.mul(lava_n, G.k(3.0)), G.k(-1.2))), G.sat(G.add(G.mul(lava_n, G.k(3.0)), G.k(-1.2))))))   # glowing cracks in a dark crust
mel.connect_material_property(lava_glow, '', MP.MP_EMISSIVE_COLOR)
mel.recompile_material(lm)
eal.save_loaded_asset(lm)


def make_mi(name, scalars, vectors):
    mi = tools.create_asset(name, ROOT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property('parent', lm)
    for k, v in scalars.items():
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in vectors.items():
        mel.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(v[0], v[1], v[2], 1))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi)
    return mi


I = LAYOUT['islands']
ember_c = I.get('ember', {}).get('pois', {}).get('caldera')
MIS = {
    # Fjord country: green lower slopes, heath, grey gneiss, snow on the high plateaus.
    'main': make_mi('MI_Land_Fjord', dict(SnowLineCm=I.get('main', {}).get('snow_line', 1150.0) * 100.0, GrassTopCm=70000.0), {}),
    'forest': make_mi('MI_Land_Forest', dict(SnowLineCm=1e7, GrassTopCm=60000.0, GrassFlatness=0.66, SandTopCm=200.0),
                      dict(GrassColor=(0.03, 0.055, 0.016), HeathColor=(0.05, 0.068, 0.025), RockColor=(0.06, 0.058, 0.05))),
    'glacier': make_mi('MI_Land_Glacier', dict(SnowLineCm=I.get('glacier', {}).get('snow_line', 520.0) * 100.0, SnowFadeCm=6000.0,
                                              GrassTopCm=30000.0, GrassFlatness=0.86, SandTopCm=250.0),
                       dict(RockColor=(0.045, 0.047, 0.052), RockColorWarm=(0.06, 0.058, 0.058), GrassColor=(0.05, 0.06, 0.03),
                            SnowColor=(0.74, 0.8, 0.88))),
    'ember': make_mi('MI_Land_Ember', dict(SnowLineCm=1e7, GrassTopCm=25000.0, GrassFlatness=0.9, SandTopCm=600.0,
                                          LavaGlow=(2.5 if ember_c else 0.0),
                                          # a 200 m lake whose edge follows the floor's bumps (glow below floor + 10 m);
                                          # tools/place_landmarks.py sets the same values and puts the dragon lair beside it
                                          LavaRadiusCm=20000.0 if ember_c else 0.0,
                                          LavaTopCm=(ember_c['z'] * 100.0 + 1000.0) if ember_c else 0.0),
                     dict(RockColor=(0.022, 0.02, 0.02), RockColorWarm=(0.06, 0.03, 0.02), SandColor=(0.018, 0.017, 0.017), LavaColor=(1.0, 0.16, 0.02),
                          GrassColor=(0.04, 0.045, 0.02), HeathColor=(0.05, 0.035, 0.025),
                          LavaCentre=((ember_c['x'] * 100.0, ember_c['y'] * 100.0, 0.0) if ember_c else (0, 0, 0)))),
}
MIS['skerry'] = make_mi('MI_Land_Skerry', dict(SnowLineCm=1e7, GrassFlatness=0.9, SandTopCm=0.0), dict(RockColor=(0.05, 0.05, 0.052)))

# ---------------------------------------------------------------- water + far-ocean skirt
wm = new_material('M_ArchipelagoWater')
W = Graph(wm)
mel.connect_material_property(W.k3((0.004, 0.012, 0.016)), '', MP.MP_BASE_COLOR)
mel.connect_material_property(W.k(0.06), '', MP.MP_ROUGHNESS)
mel.connect_material_property(W.k(0.6), '', MP.MP_SPECULAR)
wn = W.noise(0.0009, 3, -0.07, 0.07)
wn2 = W.noise(0.00025, 2, -0.07, 0.07)
a2 = W.node(unreal.MaterialExpressionAppendVector)
mel.connect_material_expressions(wn, '', a2, 'A'); mel.connect_material_expressions(wn2, '', a2, 'B')
a3 = W.node(unreal.MaterialExpressionAppendVector)
mel.connect_material_expressions(a2, '', a3, 'A'); mel.connect_material_expressions(W.k(1.0), '', a3, 'B')
mel.connect_material_property(a3, '', MP.MP_NORMAL)
mel.recompile_material(wm)
eal.save_loaded_asset(wm)

# Far ocean: same deep colour, a touch rougher (the distant sea is choppy at grazing angles), no normal detail.
fm = new_material('M_ArchipelagoFarOcean')
F = Graph(fm)
mel.connect_material_property(F.k3((0.004, 0.012, 0.016)), '', MP.MP_BASE_COLOR)
mel.connect_material_property(F.k(0.16), '', MP.MP_ROUGHNESS)
mel.connect_material_property(F.k(0.5), '', MP.MP_SPECULAR)
mel.recompile_material(fm)
eal.save_loaded_asset(fm)

# ---------------------------------------------------------------- level (World Partition)
if not levels.new_level(LEVEL, True):
    raise RuntimeError('Could not create ' + LEVEL)


def spawn(cls, loc=(0, 0, 0), rot=(0, 0, 0), label=None, folder='Archipelago', always_loaded=True):
    a = actors.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1]))
    if label:
        a.set_actor_label(label)
    a.set_folder_path(folder)
    if always_loaded:
        a.set_editor_property('is_spatially_loaded', False)
    return a


lib = unreal.DragonLandscapeLibrary
for name, isl in I.items():
    kind = isl.get('kind', name)
    mi = MIS['skerry'] if kind == 'skerry' else MIS.get(name, MIS['main'])
    loc = isl['landscape_location_cm']
    sc = isl['landscape_scale']
    ls = lib.import_heightmap_landscape(os.path.join(GEN, isl['heightmap']), isl['size_px'], unreal.Vector(*loc),
                                        unreal.Vector(*sc), mi, 'Land_' + name, 8, False)
    if not ls:
        raise RuntimeError('Landscape import failed for ' + name)
    ls.set_editor_property('tags', [unreal.Name('ArchipelagoLand'), unreal.Name('Island_' + name)])
    log('landscape %s: %d px, %.1f m/px, centre (%.0f, %.0f) m, z %.0f..%.0f m' % (
        name, isl['size_px'], isl['m_per_px'], isl['centre'][0], isl['centre'][1], isl['min_m'], isl['max_m']))
log('flushed %d landscapes' % lib.flush_landscapes())


# Verify the landscapes against the heightmaps (catches components left flat by an incomplete edit-layer merge).
import array
import random as _random
_rng = _random.Random(5)
for name, isl in I.items():
    v = array.array('H')
    with open(os.path.join(GEN, isl['heightmap']), 'rb') as f:
        v.fromfile(f, isl['size_px'] ** 2)
    n, step = isl['size_px'], isl['m_per_px'] * 100.0
    x0, y0 = isl['landscape_location_cm'][0], isl['landscape_location_cm'][1]
    bad, worst, tested = 0, 0.0, 0
    for _ in range(300):
        i, j = _rng.randrange(n), _rng.randrange(n)
        want = (v[j * n + i] - 32768.0) * isl['z_scale'] / 128.0
        res = lib.sample_landscape_height(unreal.Vector(x0 + i * step, y0 + j * step, 0.0))
        ok, got = (res if isinstance(res, tuple) else (res is not None, res))
        if not ok or got is None:
            continue
        tested += 1
        err = abs(got - want)
        worst = max(worst, err)
        bad += err > 200.0
    log('verify %s: %d samples, %d off by > 2 m, worst %.1f m' % (name, tested, bad, worst / 100.0))
    if tested == 0 or bad > tested * 0.02:
        unreal.log_error('ARCHIPELAGO_BUILD: landscape %s does not match its heightmap' % name)

water = spawn(unreal.StaticMeshActor, (0, 0, 0), label='Sea', folder='Archipelago/World')
water.static_mesh_component.set_static_mesh(eal.load_asset('/Engine/BasicShapes/Plane'))
water.static_mesh_component.set_material(0, wm)
water.set_actor_scale3d(unreal.Vector(60000, 60000, 1))       # 60 km of sea around the archipelago (a 1 m plane)
far = spawn(unreal.StaticMeshActor, (0, 0, -80), label='FarOcean', folder='Archipelago/World')
far.static_mesh_component.set_static_mesh(eal.load_asset('/Engine/BasicShapes/Plane'))
far.static_mesh_component.set_material(0, fm)
far.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
far.static_mesh_component.set_collision_profile_name('NoCollision')   # (the enable flag alone didn't stick: longships' land check hit it)
far.static_mesh_component.set_editor_property('cast_shadow', False)
far.set_actor_scale3d(unreal.Vector(400000, 400000, 1))      # 400 km skirt out to the fogged horizon

# ---------------------------------------------------------------- sky, sun, fog, clouds, grade (as Lvl_Opening)
sun = spawn(unreal.DirectionalLight, (0, 0, 500000), (-15.0, 52.0, 0), 'Sun', 'Archipelago/Lighting')
lc = sun.light_component
for k, v in (('intensity', 9.0), ('light_color', unreal.Color(255, 226, 190, 255)), ('atmosphere_sun_light', True),
             ('cast_shadows', True), ('cast_cloud_shadows', True), ('enable_light_shaft_bloom', True), ('bloom_scale', 0.25),
             ('dynamic_shadow_distance_movable_light', 60000.0), ('volumetric_scattering_intensity', 0.35),
             ('specular_scale', 0.3)):   # grazing sun specular drew cream bands on sunlit ridges seen toward the sun   # 1.5 drew cream fog bands over sunlit slopes
    lc.set_editor_property(k, v)
lc.set_mobility(unreal.ComponentMobility.MOVABLE)

spawn(unreal.SkyAtmosphere, label='SkyAtmosphere', folder='Archipelago/Lighting')
sky = spawn(unreal.SkyLight, (0, 0, 200000), label='SkyLight', folder='Archipelago/Lighting')
sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
sky.light_component.set_editor_property('real_time_capture', True)
sky.light_component.set_editor_property('intensity', 1.0)

clouds = spawn(unreal.VolumetricCloud, label='Clouds', folder='Archipelago/Lighting')
cloud_mat = eal.load_asset('/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst')
if cloud_mat:
    clouds.volumetric_cloud_component.set_editor_property('material', cloud_mat)
clouds.volumetric_cloud_component.set_editor_property('layer_bottom_altitude', 3.6)
clouds.volumetric_cloud_component.set_editor_property('layer_height', 2.5)

fog = spawn(unreal.ExponentialHeightFog, (0, 0, 0), label='Fog', folder='Archipelago/Lighting')
fc = fog.component
# Slightly denser than the opening fjord, so islands 10-20 km away read as layers of aerial perspective, and the
# sea, the skirt and the sky meet in the same haze colour at the horizon.
# Thinner and bluer than the opening fjord's fog: at 1-2 km altitude the old values turned the whole distant sea
# into a white band. The haze colour is matched to the sky just above the horizon, capped below full opacity so
# the far-ocean skirt still darkens the sea line.
for k, v in (('fog_density', 0.0035), ('fog_height_falloff', 0.2), ('fog_max_opacity', 0.9),
             ('fog_inscattering_luminance', unreal.LinearColor(0.26, 0.35, 0.48, 1)),
             ('directional_inscattering_luminance', unreal.LinearColor(0.45, 0.32, 0.2, 1)),
             ('directional_inscattering_exponent', 10.0), ('enable_volumetric_fog', True),
             ('volumetric_fog_extinction_scale', 0.25), ('start_distance', 15000.0)):
    fc.set_editor_property(k, v)

pp = spawn(unreal.PostProcessVolume, label='Grade', folder='Archipelago/Lighting')
pp.set_editor_property('unbound', True)
s = pp.settings
for k, v in (('bloom_intensity', 0.9), ('auto_exposure_bias', 0.4), ('vignette_intensity', 0.35),
             ('color_saturation', unreal.Vector4(1.06, 1.04, 1.0, 1.0)), ('color_contrast', unreal.Vector4(1.08, 1.08, 1.08, 1.0)),
             ('color_gain_shadows', unreal.Vector4(0.94, 1.0, 1.08, 1.0)), ('color_gain_highlights', unreal.Vector4(1.06, 1.0, 0.94, 1.0)),
             ('film_slope', 0.82), ('film_toe', 0.6), ('scene_fringe_intensity', 0.6), ('motion_blur_amount', 0.35)):
    s.set_editor_property('override_' + k, True)
    s.set_editor_property(k, v)
pp.set_editor_property('settings', s)

# ---------------------------------------------------------------- dragon start + POI markers + review legs
st = LAYOUT['start']
spawn(unreal.PlayerStart, (st['x'] * 100.0, st['y'] * 100.0, st['z'] * 100.0), (0, st['yaw'], 0), 'DragonStart', 'Archipelago')


def marker(label, x, y, z, tags, rot=(0, 0, 0), folder='Archipelago/POI'):
    a = spawn(unreal.TargetPoint, (x * 100.0, y * 100.0, z * 100.0), rot, label, folder)
    a.set_editor_property('tags', [unreal.Name(t) for t in tags])
    return a


for name, isl in I.items():
    for pk, p in isl.get('pois', {}).items():
        if isinstance(p, dict):
            marker('POI_%s_%s' % (name, pk), p['x'], p['y'], p.get('z', 0.0), ['POI', 'POI_%s_%s' % (name, pk)])


def bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def two_in_view(near, far, back, side):
    """Camera spot for two islands in one frame: behind the near island (as seen from the far one), offset
    sideways, looking at the far island; the near island fills the foreground to one side."""
    dx, dy = near[0] - far[0], near[1] - far[1]
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    return (near[0] + ux * back - uy * side, near[1] + uy * back + ux * side)


legs = []
def leg(name, x, y, z, yaw=0.0, pitch=0.0, dur=6.0, shots=(4.0,), aim=None, extra=()):
    tags = ['ReviewLeg:%02d' % len(legs), 'Name:' + name.replace(' ', '_'), 'Dur:%.1f' % dur,
            'Shots:' + '|'.join('%.1f' % t for t in shots), 'Pitch:%.1f' % pitch] + list(extra)
    if aim:
        tags.append('AimAt:%.0f,%.0f,%.0f' % (aim[0] * 100.0, aim[1] * 100.0, aim[2] * 100.0))
    legs.append(marker('Review_%02d_%s' % (len(legs), name.replace(' ', '_')), x, y, z, tags, (0, yaw, 0), 'Archipelago/Review'))


C = {k: v['centre'] for k, v in I.items()}
P = {k: v.get('pois', {}) for k, v in I.items()}
leg('start', st['x'], st['y'], st['z'], st['yaw'], -4.0, dur=8.0, shots=(3.0, 7.0))
if 'fjord_mouth' in P.get('main', {}):
    m = P['main']['fjord_mouth']
    leg('fjord low', m['x'], m['y'] - 900.0, 160.0, -90.0, -2.0, dur=7.0, shots=(5.0,))
if 'forest' in C:
    # Crossing: leave the main island's east coast and fly to the forest isle at speed (~4 km of open sea).
    sx = C['main'][0] + I['main']['size_m'] * 0.47
    leg('crossing to forest', sx, C['forest'][1] * 0.6, 340.0, bearing((sx, C['forest'][1] * 0.6), C['forest']), -1.0,
        dur=30.0, shots=(3.0, 12.0, 21.0, 29.0), aim=(C['forest'][0], C['forest'][1], 200.0), extra=('Speed:430',))
if 'forest' in C and 'ember' in C:
    p = two_in_view(C['forest'], C['ember'], 4200.0, 1900.0)
    leg('two islands forest ember', p[0], p[1], 700.0, 0.0, -5.0, dur=5.0, shots=(3.5,), aim=(C['ember'][0], C['ember'][1], 300.0))
if 'glacier' in C:
    p = two_in_view(C['glacier'], C['main'], 4600.0, -2200.0)
    leg('two islands glacier main', p[0], p[1], 1100.0, 0.0, -5.0, dur=5.0, shots=(3.5,), aim=(C['main'][0], C['main'][1], 300.0))
if 'waterfall' in P.get('forest', {}):
    w = P['forest']['waterfall']
    leg('forest waterfall', w['x'] + 900.0, w['y'] + 250.0, max(w['z'] * 0.8, 60.0), 0.0, -3.0, dur=5.0, shots=(3.5,),
        aim=(w['x'], w['y'], w['z'] * 0.5), extra=('Speed:120',))
if 'village' in P.get('forest', {}):
    v = P['forest']['village']
    leg('forest village', v['x'] - 1400.0, v['y'] + 200.0, 120.0, 0.0, -4.0, dur=5.0, shots=(4.0,), aim=(v['x'], v['y'], 10.0),
        extra=('Speed:140',))
if 'summit' in P.get('glacier', {}):
    s_ = P['glacier']['summit']
    a = math.radians(bearing(C['glacier'], (s_['x'], s_['y'])) + 150.0)
    leg('glacier peaks', s_['x'] + 2600.0 * math.cos(a), s_['y'] + 2600.0 * math.sin(a), s_['z'] * 0.75, 0.0, 0.0, dur=5.0,
        shots=(3.5,), aim=(s_['x'], s_['y'], s_['z'] * 0.7), extra=('Speed:140',))
if 'caldera' in P.get('ember', {}):
    c_ = P['ember']['caldera']
    leg('ember volcano', c_['x'] - 3000.0, c_['y'] + 2200.0, c_['rim_z'] * 0.7, 0.0, 0.0, dur=5.0, shots=(3.5,),
        aim=(c_['x'], c_['y'], c_['rim_z'] * 0.8), extra=('Speed:150',))
    leg('ember caldera', c_['x'] - 750.0, c_['y'] + 150.0, c_['rim_z'] + 520.0, 0.0, -30.0, dur=4.0, shots=(2.5,),
        aim=(c_['x'], c_['y'], c_['z']), extra=('Speed:80', 'Orbit:0,-48'))
if 'village' in P.get('main', {}):
    v = P['main']['village']
    leg('main village', v['x'], v['y'] + 1500.0, 110.0, -90.0, -4.0, dur=5.0, shots=(4.0,), aim=(v['x'], v['y'], 10.0),
        extra=('Speed:140',))
# Horizon at altitude: 1.6 km up over the main island, level, looking east over the archipelago, then west to open sea.
leg('horizon east', C['main'][0] - 3000.0, C['main'][1], 1600.0, 0.0, 0.0, dur=4.0, shots=(3.0,))
leg('horizon west', C['main'][0] - 6500.0, C['main'][1] + 2000.0, 1600.0, 180.0, 0.0, dur=4.0, shots=(3.0,))
# Plunge check: dive into the open sea between the islands, burst back out.
leg('plunge', 7600.0, 7700.0, 380.0, 0.0, -10.0, dur=9.0,   # deep open sea between the main and ember isles
    shots=(2.2, 4.0, 5.2, 7.5), extra=('Dive:0.6', 'Orbit:150,-10'))
# The fleet leg is added by tools/place_archipelago.py, which knows where the ships are.
# Overview of the main island's east half from high up (checks every landscape section streams in).
leg('main east overview', 4500.0, 1500.0, 3200.0, -90.0, -55.0, dur=4.0, shots=(3.0,), extra=('Speed:100', 'Orbit:0,-60'))
log('%d review legs' % len(legs))

world = unreal.EditorLevelLibrary.get_editor_world()
ws = world.get_world_settings()
ws.set_editor_property('default_game_mode', unreal.load_class(None, '/Script/DragonRider.DragonRiderGameMode'))
ws.set_editor_property('kill_z', -100000.0)

if not levels.save_current_level():
    raise RuntimeError('Level save failed')
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
log('saved %s (start %.0f, %.0f yaw %.0f)' % (LEVEL, st['x'], st['y'], st['yaw']))
unreal.log('ARCHIPELAGO_LEVEL_SAVED')

PLACE = os.path.normpath(os.path.join(PROJECT_DIR, '..', '..', 'tools', 'place_archipelago.py'))
if eal.does_directory_exist('/Game/DragonRider/World/Meshes') and os.path.exists(PLACE):
    exec(compile(open(PLACE, encoding='utf-8').read(), PLACE, 'exec'), {'__name__': '__main__'})
else:
    unreal.log_warning('ARCHIPELAGO_BUILD: world kit or place_archipelago.py missing; skipped villages/fleet')
