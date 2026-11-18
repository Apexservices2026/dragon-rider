"""Build the opening level: a Viking dragon rider flying into a Nordic fjord at golden hour.

Run headless (rebuilds everything under /Game/DragonRider/Opening; nothing else is touched):
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Requires Saved/Generated/SM_FjordTerrain.fbx from tools/blender/gen_fjord_terrain.py.
"""
import math
import os
import unreal

ROOT = '/Game/DragonRider/Opening'
LEVEL = ROOT + '/Lvl_Opening'
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
FBX = os.path.join(PROJECT_DIR, 'Saved', 'Generated', 'SM_FjordTerrain.fbx')

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty


def log(msg):
    unreal.log('OPENING_BUILD: ' + msg)


# ---------------------------------------------------------------- clean previous build of OUR folder only
if eal.does_directory_exist(ROOT):
    eal.delete_directory(ROOT)
eal.make_directory(ROOT)

# ---------------------------------------------------------------- terrain import
if not os.path.exists(FBX):
    raise RuntimeError('Missing terrain FBX: ' + FBX)
task = unreal.AssetImportTask()
task.filename = FBX
task.destination_path = ROOT
task.destination_name = 'SM_FjordTerrain'
task.automated = True
task.save = False
task.replace_existing = True
ui = unreal.FbxImportUI()
ui.import_mesh = True
ui.import_materials = False
ui.import_textures = False
ui.import_as_skeletal = False
ui.static_mesh_import_data.combine_meshes = True
ui.static_mesh_import_data.vertex_color_import_option = unreal.VertexColorImportOption.REPLACE
ui.static_mesh_import_data.generate_lightmap_u_vs = False
ui.static_mesh_import_data.auto_generate_collision = False
task.options = ui
tools.import_asset_tasks([task])
terrain = eal.load_asset(ROOT + '/SM_FjordTerrain')
if not terrain:
    found = [p for p in eal.list_assets(ROOT, recursive=True) if 'Terrain' in p]
    raise RuntimeError('Terrain import failed; found: %s' % found)

nanite = terrain.get_editor_property('nanite_settings')
nanite.set_editor_property('enabled', False)   # full-res LOD0 (Nanite path rendered only its coarse fallback here)
terrain.set_editor_property('nanite_settings', nanite)
body = terrain.get_editor_property('body_setup')
if body:
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
bounds = terrain.get_bounds()
log('terrain bounds extent %s' % bounds.box_extent)


# ---------------------------------------------------------------- materials
def new_material(name):
    return tools.create_asset(name, ROOT, unreal.Material, unreal.MaterialFactoryNew())


def expr(mat, cls, x, y):
    return mel.create_material_expression(mat, cls, x, y)


def const(mat, v, x, y):
    e = expr(mat, unreal.MaterialExpressionConstant, x, y)
    e.set_editor_property('r', v)
    return e


def const3(mat, rgb, x, y):
    e = expr(mat, unreal.MaterialExpressionConstant3Vector, x, y)
    e.set_editor_property('constant', unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    return e


def world_noise(mat, scale, levels, x, y, out_min=0.0, out_max=1.0):
    n = expr(mat, unreal.MaterialExpressionNoise, x, y)
    n.set_editor_property('scale', scale)
    n.set_editor_property('levels', levels)
    n.set_editor_property('output_min', out_min)
    n.set_editor_property('output_max', out_max)
    n.set_editor_property('quality', 1)
    return n


# Terrain: coloured procedurally from world height and slope (rock / moss / snow / wet shore),
# with world-space noise and vertical erosion streaks to break up the 15 m vertex spacing.
tm = new_material('M_FjordTerrain')
_y = [0]
def node(cls):
    _y[0] += 90
    return expr(tm, cls, -1200 + (_y[0] // 900) * 250, _y[0] % 900)
def op(cls, a, b, a_out='', b_out=''):
    n = node(cls)
    mel.connect_material_expressions(a, a_out, n, 'A')
    mel.connect_material_expressions(b, b_out, n, 'B')
    return n
def sat(a):
    n = node(unreal.MaterialExpressionSaturate)
    mel.connect_material_expressions(a, '', n, '')
    return n
def lerp(a, b, alpha):
    n = node(unreal.MaterialExpressionLinearInterpolate)
    mel.connect_material_expressions(a, '', n, 'A')
    mel.connect_material_expressions(b, '', n, 'B')
    mel.connect_material_expressions(alpha, '', n, 'Alpha')
    return n
def k(v): return const(tm, v, -1400, 0)
def k3(c): return const3(tm, c, -1400, 0)
M, A, S = unreal.MaterialExpressionMultiply, unreal.MaterialExpressionAdd, unreal.MaterialExpressionSubtract

wp = node(unreal.MaterialExpressionWorldPosition)
z = node(unreal.MaterialExpressionComponentMask)
z.set_editor_property('r', False); z.set_editor_property('g', False); z.set_editor_property('b', True)
mel.connect_material_expressions(wp, '', z, '')
nrm = node(unreal.MaterialExpressionVertexNormalWS)
flat = node(unreal.MaterialExpressionComponentMask)
flat.set_editor_property('r', False); flat.set_editor_property('g', False); flat.set_editor_property('b', True)
mel.connect_material_expressions(nrm, '', flat, '')

big = world_noise(tm, 0.0006, 4, -900, 900, 0.0, 1.0)        # ~kilometre-scale variation
mid = world_noise(tm, 0.0035, 3, -900, 1000, 0.7, 1.25)
fine = world_noise(tm, 0.03, 2, -900, 1100, 0.85, 1.12)
sq = op(M, wp, k3((1.0, 1.0, 0.1)))
streak = world_noise(tm, 0.003, 3, -900, 1200, 0.55, 1.2)
mel.connect_material_expressions(sq, '', streak, 'Position')

rock = op(M, op(M, op(M, k3((0.05, 0.048, 0.05)), mid), fine), streak)
rock = lerp(rock, op(M, rock, k3((1.25, 1.05, 0.8))), big)             # warm/cold rock patches
moss_c = lerp(k3((0.045, 0.06, 0.018)), k3((0.075, 0.06, 0.03)), big)
moss_mask = op(M, op(M, sat(op(M, op(S, flat, k(0.8)), k(8.0))), sat(op(M, op(S, k(70000.0), z), k(1.0 / 30000.0)))),
               sat(op(M, z, k(1.0 / 1500.0))))
col = lerp(rock, op(M, moss_c, fine), moss_mask)
snow_line = op(A, k(105000.0), op(M, big, k(-35000.0)))
snow_mask = op(M, sat(op(M, op(S, z, snow_line), k(1.0 / 9000.0))), sat(op(M, op(S, flat, k(0.42)), k(5.0))))
snow_mask = op(A, snow_mask, op(M, sat(op(M, op(S, z, k(170000.0)), k(1.0 / 20000.0))), sat(op(M, op(S, flat, k(0.2)), k(4.0)))))
col = lerp(col, op(M, k3((0.78, 0.81, 0.87)), fine), sat(snow_mask))
wet = sat(op(M, op(S, k(1200.0), z), k(1.0 / 1200.0)))
col = lerp(col, k3((0.02, 0.019, 0.018)), wet)
mel.connect_material_property(col, '', MP.MP_BASE_COLOR)
mel.connect_material_property(lerp(lerp(k(0.92), k(0.6), sat(snow_mask)), k(0.3), wet), '', MP.MP_ROUGHNESS)
mel.recompile_material(tm)

# Water: deep dark green-blue, glossy, with world-space noise ripples in the normal.
wm = new_material('M_FjordWater')
mel.connect_material_property(const3(wm, (0.004, 0.012, 0.016), -500, 0), '', MP.MP_BASE_COLOR)
mel.connect_material_property(const(wm, 0.06, -500, 150), '', MP.MP_ROUGHNESS)
mel.connect_material_property(const(wm, 0.6, -500, 220), '', MP.MP_SPECULAR)
wn = world_noise(wm, 0.0009, 3, -900, 300, -0.07, 0.07)
wn2 = world_noise(wm, 0.00025, 2, -900, 500, -0.07, 0.07)
nrm = expr(wm, unreal.MaterialExpressionAppendVector, -600, 350)
mel.connect_material_expressions(wn, '', nrm, 'A')
mel.connect_material_expressions(wn2, '', nrm, 'B')
nrm3 = expr(wm, unreal.MaterialExpressionAppendVector, -400, 350)
mel.connect_material_expressions(nrm, '', nrm3, 'A')
mel.connect_material_expressions(const(wm, 1.0, -600, 450), '', nrm3, 'B')
mel.connect_material_property(nrm3, '', MP.MP_NORMAL)
mel.recompile_material(wm)

terrain.set_material(0, tm)
for a in (terrain, tm, wm):
    eal.save_loaded_asset(a)

# ---------------------------------------------------------------- level
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not levels.new_level(LEVEL):
    raise RuntimeError('Could not create ' + LEVEL)


def spawn(cls, loc=(0, 0, 0), rot=(0, 0, 0), label=None, folder='Opening'):
    a = actors.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1]))
    if label:
        a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


t = spawn(unreal.StaticMeshActor, label='FjordTerrain', folder='Opening/World')
t.static_mesh_component.set_static_mesh(terrain)
t.static_mesh_component.set_material(0, tm)

water = spawn(unreal.StaticMeshActor, (0, 0, 0), label='Sea', folder='Opening/World')
water.static_mesh_component.set_static_mesh(eal.load_asset('/Engine/BasicShapes/Plane'))
water.static_mesh_component.set_material(0, wm)
water.set_actor_scale3d(unreal.Vector(30000, 30000, 1))   # 30 km of sea (a 1 m plane); larger breaks the water shading

# Golden-hour sun low in the south-west, behind-left of the player's opening heading (east).
sun = spawn(unreal.DirectionalLight, (0, 0, 500000), (-15.0, 52.0, 0), 'Sun', 'Opening/Lighting')
lc = sun.light_component
lc.set_editor_property('intensity', 9.0)
lc.set_editor_property('light_color', unreal.Color(255, 226, 190, 255))
lc.set_editor_property('atmosphere_sun_light', True)
lc.set_editor_property('cast_shadows', True)
lc.set_editor_property('cast_cloud_shadows', True)
lc.set_editor_property('enable_light_shaft_bloom', True)
lc.set_editor_property('bloom_scale', 0.25)
lc.set_editor_property('dynamic_shadow_distance_movable_light', 60000.0)
lc.set_editor_property('volumetric_scattering_intensity', 1.5)
lc.set_mobility(unreal.ComponentMobility.MOVABLE)

spawn(unreal.SkyAtmosphere, label='SkyAtmosphere', folder='Opening/Lighting')
sky = spawn(unreal.SkyLight, (0, 0, 200000), label='SkyLight', folder='Opening/Lighting')
sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
sky.light_component.set_editor_property('real_time_capture', True)
sky.light_component.set_editor_property('intensity', 1.0)

clouds = spawn(unreal.VolumetricCloud, label='Clouds', folder='Opening/Lighting')
cloud_mat = eal.load_asset('/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst')
if cloud_mat:
    clouds.volumetric_cloud_component.set_editor_property('material', cloud_mat)
cc = clouds.volumetric_cloud_component
cc.set_editor_property('layer_bottom_altitude', 3.6)
cc.set_editor_property('layer_height', 2.5)

fog = spawn(unreal.ExponentialHeightFog, (0, 0, 0), label='Fog', folder='Opening/Lighting')
fc = fog.component
fc.set_editor_property('fog_density', 0.006)
fc.set_editor_property('fog_height_falloff', 0.25)
fc.set_editor_property('fog_inscattering_luminance', unreal.LinearColor(0.42, 0.52, 0.66, 1))
fc.set_editor_property('directional_inscattering_luminance', unreal.LinearColor(1.0, 0.62, 0.32, 1))
fc.set_editor_property('directional_inscattering_exponent', 8.0)
fc.set_editor_property('enable_volumetric_fog', True)
fc.set_editor_property('volumetric_fog_extinction_scale', 0.25)
fc.set_editor_property('start_distance', 8000.0)

pp = spawn(unreal.PostProcessVolume, label='Grade', folder='Opening/Lighting')
pp.set_editor_property('unbound', True)
s = pp.settings
for k, v in (('bloom_intensity', 0.9), ('auto_exposure_bias', 0.4), ('vignette_intensity', 0.35),
             ('color_saturation', unreal.Vector4(1.06, 1.04, 1.0, 1.0)), ('color_contrast', unreal.Vector4(1.08, 1.08, 1.08, 1.0)),
             ('color_gain_shadows', unreal.Vector4(0.94, 1.0, 1.08, 1.0)), ('color_gain_highlights', unreal.Vector4(1.06, 1.0, 0.94, 1.0)),
             ('film_slope', 0.82), ('film_toe', 0.6), ('scene_fringe_intensity', 0.6), ('motion_blur_amount', 0.35)):
    s.set_editor_property('override_' + k, True)
    s.set_editor_property(k, v)
pp.set_editor_property('settings', s)

# Player start: out over the open sea, looking at the fjord mouth with the first village (Skerholm) in view.
# The imported terrain's Y is mirrored relative to the Blender centre() formula, so everything is derived from
# the real terrain vertices: the mouth is the longest water run across x = -5200 m, and the start is the open-sea
# point (x <= -7600 m) with clear line of sight to both the village and the mouth and the tightest angle between them.
md = terrain.get_static_mesh_description(0)
GN = int(round(math.sqrt(md.get_vertex_count())))
GSTEP = 1600000.0 / (GN - 1)
HG = [0.0] * (GN * GN)
for i in range(md.get_vertex_count()):
    p = md.get_vertex_position(unreal.VertexID(i))
    HG[int(round((p.y + 800000.0) / GSTEP)) * GN + int(round((p.x + 800000.0) / GSTEP))] = p.z / 100.0
def ground(x, y):  # metres
    i = min(GN - 1, max(0, int(round((x * 100.0 + 800000.0) / GSTEP))))
    j = min(GN - 1, max(0, int(round((y * 100.0 + 800000.0) / GSTEP))))
    return HG[j * GN + i]
def clear(a, b, za, zb):
    return all(ground(a[0] + (b[0] - a[0]) * t / 200.0, a[1] + (b[1] - a[1]) * t / 200.0) < za + (zb - za) * t / 200.0 - 3.0 for t in range(1, 200))
runs, start_y = [], None
for k in range(-300, 301):
    y = k * 10.0
    if ground(-5200.0, y) < -1.0 and start_y is None:
        start_y = y
    elif ground(-5200.0, y) >= -1.0 and start_y is not None:
        runs.append((y - start_y, start_y, y)); start_y = None
_, y0, y1 = max(runs)
mouth = (-5200.0, (y0 + y1) / 2.0)
FIRST_VILLAGE = (-6156.0, -1406.0)  # Skerholm, see tools/place_world.py
START_ALT = 400.0
def bearing(f, p): return math.degrees(math.atan2(p[1] - f[1], p[0] - f[0]))
best = None
for x in range(-8000, -7550, 100):
    for y in range(-3000, 1600, 100):
        f = (float(x), float(y))
        if ground(*f) > -5.0 or not clear(f, FIRST_VILLAGE, START_ALT, 15.0) or not clear(f, mouth, START_ALT, 40.0):
            continue
        spread = abs(bearing(f, mouth) - bearing(f, FIRST_VILLAGE))
        if best is None or spread < best[0]:
            best = (spread, f)
if not best:
    raise RuntimeError('No open-sea start with a view of the fjord mouth and the first village')
(FJ_X, fj_y) = best[1]
heading = (bearing(best[1], mouth) + bearing(best[1], FIRST_VILLAGE)) / 2.0
log('fjord mouth at (%.0f, %.0f) m; start (%.0f, %.0f) heading %.1f (mouth %.1f, village %.1f)' % (
    mouth[0], mouth[1], FJ_X, fj_y, heading, bearing(best[1], mouth), bearing(best[1], FIRST_VILLAGE)))
spawn(unreal.PlayerStart, (FJ_X * 100.0, fj_y * 100.0, START_ALT * 100.0), (0, heading, 0), 'DragonStart', 'Opening')

world = unreal.EditorLevelLibrary.get_editor_world()
ws = world.get_world_settings()
gm = unreal.load_class(None, '/Script/DragonRider.DragonRiderGameMode')
ws.set_editor_property('default_game_mode', gm)
ws.set_editor_property('kill_z', -100000.0)

if not levels.save_current_level():
    raise RuntimeError('Level save failed')
log('saved %s (start %.0f, %.0f heading %.1f)' % (LEVEL, FJ_X, fj_y, heading))
unreal.log('OPENING_LEVEL_SAVED')

# ---------------------------------------------------------------- villages + longship fleet (needs tools/import_world_kit.py run once)
PLACE = os.path.normpath(os.path.join(PROJECT_DIR, '..', '..', 'tools', 'place_world.py'))
if eal.does_directory_exist('/Game/DragonRider/World/Meshes'):
    exec(compile(open(PLACE, encoding='utf-8').read(), PLACE, 'exec'), {'__name__': '__main__'})
else:
    unreal.log_warning('OPENING_BUILD: world kit not imported; skipped villages/fleet (run tools/import_world_kit.py, then rebuild)')
