"""Import Vertex's island landmark kit (manifest "landmarks" section) into /Game/DragonRider/World/Landmarks.

Run headless after tools/import_world_kit.py (rebuilds only /Game/DragonRider/World/Landmarks):
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Requires Saved/Generated/World/SM_*.fbx, *.png and props_manifest.json from tools/blender/world/build_landmarks.py.

Materials use the world kit's masters (/Game/DragonRider/World/Materials):
- M_VikingKit gets an optional emissive input (Emissive texture x EmissiveColor x EmissiveStrength, default off,
  added once and idempotently, so the existing kit instances look exactly as before). Lava rock, obsidian,
  crystal, charred wood, runes and ice set it from their *_E.png maps.
- Water and foam (manifest "translucent_two_sided") need translucency, which the opaque masters can't do, so
  they get one more master in the same folder, M_VikingKit_Water: two-sided translucent, BC alpha = opacity,
  with the texture panned down V (WaterSpeed) so the falls flow.
- Sets the landmarks share with the kit (manifest "shared_from_kit") reuse the kit's existing instances.
"""
import json
import os
import sys
import unreal

WORLD = '/Game/DragonRider/World'
ROOT = WORLD + '/Landmarks'
TEX = ROOT + '/Textures'
MAT = ROOT + '/Materials'
MESH = ROOT + '/Meshes'
KIT_MAT = WORLD + '/Materials'
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SRC = os.path.join(PROJECT_DIR, 'Saved', 'Generated', 'World')

sys.path.insert(0, os.path.normpath(os.path.join(PROJECT_DIR, '..', '..', 'tools')))
import collision_rules  # noqa: E402

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty

EMISSIVE = {'M_LavaRock': 4.0, 'M_Obsidian': 5.0, 'M_Crystal': 1.5, 'M_Charred': 6.0, 'M_Runes': 0.8, 'M_Ice': 1.5}
METALLIC = {'M_Iron': 0.6}
# Collision rules live in tools/collision_rules.py (shared with import_world_kit.py).
# Emissive tint per set (the ice glow map reads magenta in the golden-hour grade; tint it to icy blue).
EMISSIVE_TINT = {'M_Ice': (0.25, 0.65, 1.0)}


def log(msg):
    unreal.log('LANDMARK_IMPORT: ' + msg)


manifest = json.load(open(os.path.join(SRC, 'props_manifest.json'), encoding='utf-8'))
LM = manifest['landmarks']
translucent = set(LM.get('translucent_two_sided', []))
shared = set(LM.get('shared_from_kit', []))

master = eal.load_asset(KIT_MAT + '/M_VikingKit')
if not master:
    raise RuntimeError('Run tools/import_world_kit.py first (M_VikingKit missing)')

# ---------------------------------------------------------------- clean previous build of OUR folder only
if eal.does_directory_exist(ROOT):
    eal.delete_directory(ROOT)
for d in (ROOT, TEX, MAT, MESH):
    eal.make_directory(d)


def run_import(filename, dest, name, options=None):
    task = unreal.AssetImportTask()
    task.filename = filename
    task.destination_path = dest
    task.destination_name = name
    task.automated = True
    task.save = False
    task.replace_existing = True
    if options:
        task.options = options
    tools.import_asset_tasks([task])
    asset = eal.load_asset(dest + '/' + name)
    if not asset:
        raise RuntimeError('Import failed: ' + filename)
    return asset


textures = {}
def texture(png, kind):
    name = os.path.splitext(png)[0]
    if name in textures:
        return textures[name]
    kit = eal.load_asset(WORLD + '/Textures/' + name) if eal.does_asset_exist(WORLD + '/Textures/' + name) else None
    if kit:
        textures[name] = kit
        return kit
    half = os.path.join(SRC, 'half', png)          # 1024 px copy from tools/halve_landmark_textures.py, if made
    t = run_import(half if os.path.exists(half) else os.path.join(SRC, png), TEX, name)
    if kind == 'normal':
        t.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        t.set_editor_property('srgb', False)
    elif kind == 'rough':
        t.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_GRAYSCALE)
        t.set_editor_property('srgb', False)
    else:
        t.set_editor_property('srgb', True)
    eal.save_loaded_asset(t)
    textures[name] = t
    return t


# ---------------------------------------------------------------- M_VikingKit: optional emissive (idempotent)
if 'Emissive' not in [str(n) for n in mel.get_texture_parameter_names(master)]:
    e_tex = mel.create_material_expression(master, unreal.MaterialExpressionTextureSampleParameter2D, -700, 1100)
    e_tex.set_editor_property('parameter_name', 'Emissive')
    e_tex.set_editor_property('texture', unreal.load_asset('/Engine/EngineResources/Black'))
    e_col = mel.create_material_expression(master, unreal.MaterialExpressionVectorParameter, -700, 1400)
    e_col.set_editor_property('parameter_name', 'EmissiveColor')
    e_col.set_editor_property('default_value', unreal.LinearColor(1, 1, 1, 1))
    e_str = mel.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -700, 1550)
    e_str.set_editor_property('parameter_name', 'EmissiveStrength')
    e_str.set_editor_property('default_value', 0.0)
    m1 = mel.create_material_expression(master, unreal.MaterialExpressionMultiply, -350, 1100)
    mel.connect_material_expressions(e_tex, 'RGB', m1, 'A')
    mel.connect_material_expressions(e_col, '', m1, 'B')
    m2 = mel.create_material_expression(master, unreal.MaterialExpressionMultiply, -200, 1100)
    mel.connect_material_expressions(m1, '', m2, 'A')
    mel.connect_material_expressions(e_str, '', m2, 'B')
    mel.connect_material_property(m2, '', MP.MP_EMISSIVE_COLOR)
    mel.recompile_material(master)
    eal.save_loaded_asset(master)
    log('added optional emissive to M_VikingKit')

# ---------------------------------------------------------------- M_VikingKit_Water (translucent, panning)
water_master = None
if translucent:
    path = KIT_MAT + '/M_VikingKit_Water'
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    wm = tools.create_asset('M_VikingKit_Water', KIT_MAT, unreal.Material, unreal.MaterialFactoryNew())
    wm.set_editor_property('two_sided', True)
    wm.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
    wm.set_editor_property('translucency_lighting_mode', unreal.TranslucencyLightingMode.TLM_SURFACE)
    sample = textures.get('T_Waterfall_BC') or texture('T_Waterfall_BC.png', 'bc')
    uv = mel.create_material_expression(wm, unreal.MaterialExpressionTextureCoordinate, -1100, 0)
    pan = mel.create_material_expression(wm, unreal.MaterialExpressionPanner, -900, 0)
    spd = mel.create_material_expression(wm, unreal.MaterialExpressionScalarParameter, -1100, 150)
    spd.set_editor_property('parameter_name', 'WaterSpeed'); spd.set_editor_property('default_value', 0.45)
    ap = mel.create_material_expression(wm, unreal.MaterialExpressionAppendVector, -1000, 150)
    mel.connect_material_expressions(mel.create_material_expression(wm, unreal.MaterialExpressionConstant, -1200, 150), '', ap, 'A')
    mel.connect_material_expressions(spd, '', ap, 'B')
    mel.connect_material_expressions(uv, '', pan, 'Coordinate')
    mel.connect_material_expressions(ap, '', pan, 'Speed')
    bc = mel.create_material_expression(wm, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0)
    bc.set_editor_property('parameter_name', 'BaseColor'); bc.set_editor_property('texture', sample)
    mel.connect_material_expressions(pan, '', bc, 'UVs')
    nr = mel.create_material_expression(wm, unreal.MaterialExpressionTextureSampleParameter2D, -700, 300)
    nr.set_editor_property('parameter_name', 'Normal')
    nr.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    nr.set_editor_property('texture', unreal.load_asset('/Engine/EngineMaterials/FlatNormal'))
    mel.connect_material_expressions(pan, '', nr, 'UVs')
    tint = mel.create_material_expression(wm, unreal.MaterialExpressionVectorParameter, -700, -250)
    tint.set_editor_property('parameter_name', 'Tint'); tint.set_editor_property('default_value', unreal.LinearColor(1, 1, 1, 1))
    mul = mel.create_material_expression(wm, unreal.MaterialExpressionMultiply, -350, 0)
    mel.connect_material_expressions(bc, 'RGB', mul, 'A'); mel.connect_material_expressions(tint, '', mul, 'B')
    mel.connect_material_property(mul, '', MP.MP_BASE_COLOR)
    op = mel.create_material_expression(wm, unreal.MaterialExpressionScalarParameter, -700, 500)
    op.set_editor_property('parameter_name', 'Opacity'); op.set_editor_property('default_value', 0.85)
    om = mel.create_material_expression(wm, unreal.MaterialExpressionMultiply, -350, 450)
    mel.connect_material_expressions(bc, 'A', om, 'A'); mel.connect_material_expressions(op, '', om, 'B')
    mel.connect_material_property(om, '', MP.MP_OPACITY)
    mel.connect_material_property(nr, 'RGB', MP.MP_NORMAL)
    rough = mel.create_material_expression(wm, unreal.MaterialExpressionConstant, -350, 650)
    rough.set_editor_property('r', 0.15)
    mel.connect_material_property(rough, '', MP.MP_ROUGHNESS)
    mel.recompile_material(wm)
    eal.save_loaded_asset(wm)
    water_master = wm

# ---------------------------------------------------------------- material instances per texture set
sets = {}
for prop in LM['props']:
    for mname, files in prop.get('materials', {}).items():
        sets[mname] = files
instances = {}
for mname, files in sorted(sets.items()):
    kit_mi = KIT_MAT + '/MI_' + mname[2:]
    if mname in shared and eal.does_asset_exist(kit_mi):
        instances[mname] = eal.load_asset(kit_mi)
        continue
    # files: BC, N, N_DX, R and (for glowing sets) E - pick each by its suffix, not by position
    bc = next(f for f in files if f.endswith('_BC.png'))
    n = next((f for f in files if f.endswith('_N.png')), files[1])
    r = next((f for f in files if f.endswith('_R.png')), files[-1])
    n_dx = n.replace('_N.png', '_N_DX.png')
    mi = tools.create_asset('MI_' + mname[2:], MAT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mname in translucent:
        mi.set_editor_property('parent', water_master)
        mel.set_material_instance_texture_parameter_value(mi, 'BaseColor', texture(bc, 'bc'))
        if os.path.exists(os.path.join(SRC, n_dx)):
            mel.set_material_instance_texture_parameter_value(mi, 'Normal', texture(n_dx, 'normal'))
        if mname == 'M_Foam':
            mel.set_material_instance_scalar_parameter_value(mi, 'WaterSpeed', 0.08)
            mel.set_material_instance_scalar_parameter_value(mi, 'Opacity', 0.7)
    else:
        mi.set_editor_property('parent', master)
        for pname, png, kind in (('BaseColor', bc, 'bc'), ('Normal', n_dx, 'normal'), ('Roughness', r, 'rough')):
            mel.set_material_instance_texture_parameter_value(mi, pname, texture(png, kind))
        mel.set_material_instance_scalar_parameter_value(mi, 'Metallic', METALLIC.get(mname, 0.0))
        e_png = bc.replace('_BC.png', '_E.png')
        if mname in EMISSIVE and os.path.exists(os.path.join(SRC, e_png)):
            mel.set_material_instance_texture_parameter_value(mi, 'Emissive', texture(e_png, 'bc'))
            mel.set_material_instance_scalar_parameter_value(mi, 'EmissiveStrength', EMISSIVE[mname])
            if mname in EMISSIVE_TINT:
                mel.set_material_instance_vector_parameter_value(mi, 'EmissiveColor', unreal.LinearColor(*EMISSIVE_TINT[mname], 1.0))
    eal.save_loaded_asset(mi)
    instances[mname] = mi
log('%d material instances (%d shared with the kit), %d textures' % (len(instances), len([m for m in instances if m in shared]), len(textures)))


# ---------------------------------------------------------------- meshes
def fbx_options():
    ui = unreal.FbxImportUI()
    ui.import_mesh = True
    ui.import_materials = False
    ui.import_textures = False
    ui.import_as_skeletal = False
    sd = ui.static_mesh_import_data
    sd.combine_meshes = True
    sd.generate_lightmap_u_vs = False
    sd.auto_generate_collision = False
    sd.remove_degenerates = True
    sd.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS
    return ui


for prop in LM['props']:
    name = os.path.splitext(prop['fbx'])[0]
    mesh = run_import(os.path.join(SRC, prop['fbx']), MESH, name, fbx_options())
    missing = []
    is_water = False
    for i, slot in enumerate(mesh.static_materials):
        sname = str(slot.material_slot_name)
        key = sname if sname in instances else next((k for k in sorted(instances, key=len, reverse=True) if sname.startswith(k)), None)
        if key:
            mesh.set_material(i, instances[key])
            is_water = is_water or key in translucent
        else:
            missing.append(sname)
    nanite = mesh.get_editor_property('nanite_settings')
    nanite.set_editor_property('enabled', not is_water)     # Nanite can't draw translucent materials
    mesh.set_editor_property('nanite_settings', nanite)
    kind, n_prims = collision_rules.apply(mesh)
    eal.save_loaded_asset(mesh)
    b = mesh.get_bounding_box()
    log('%s slots=%d missing=%s nanite=%d size=(%.0f,%.0f,%.0f) collision=%s/%d prims' % (
        name, len(mesh.static_materials), missing, 0 if is_water else 1, b.max.x - b.min.x, b.max.y - b.min.y, b.max.z - b.min.z,
        kind, n_prims))

# Drop the machine-specific source paths Interchange stores in the import data (tools/scrub_import_paths.py).
import sys as _sys
_sys.path.insert(0, os.path.normpath(os.path.join(PROJECT_DIR, '..', '..', 'tools')))
import scrub_import_paths
scrub_import_paths.scrub_folders([ROOT])
unreal.log('LANDMARKS_IMPORTED')
