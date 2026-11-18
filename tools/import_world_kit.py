"""Import Vertex's Viking world kit (longships, village buildings, props) into /Game/DragonRider/World.

Run headless (rebuilds everything under /Game/DragonRider/World; nothing else is touched):
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Requires Saved/Generated/World/*.fbx, *.png and props_manifest.json from tools/blender/world/*.py.

Materials: one opaque master (M_VikingKit) and one two-sided master (M_VikingKit_TwoSided, for sails and
banners), with a material instance per texture set in the manifest (BaseColor sRGB, DirectX normal map,
linear roughness; iron gets metallic 0.6). Meshes get Nanite on and simple box collision on buildings.
"""
import json
import os
import unreal

ROOT = '/Game/DragonRider/World'
TEX = ROOT + '/Textures'
MAT = ROOT + '/Materials'
MESH = ROOT + '/Meshes'
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SRC = os.path.join(PROJECT_DIR, 'Saved', 'Generated', 'World')

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty

# Meshes that get a simple box collision (buildings, piers, palisade); small props and ship parts get none.
COLLIDE = {'SM_Longhouse', 'SM_Hut', 'SM_Storehouse', 'SM_Smithy', 'SM_PierSection', 'SM_PierEnd',
           'SM_PalisadeWall', 'SM_PalisadeGate', 'SM_Watchtower'}
METALLIC = {'M_Iron': 0.6}
# Per-set colour trims so the kit sits in the graded golden-hour scene (turf read as neon green unmodified).
TINT = {'M_Turf': (0.46, 0.43, 0.3)}


def log(msg):
    unreal.log('WORLD_IMPORT: ' + msg)


with open(os.path.join(SRC, 'props_manifest.json'), encoding='utf-8') as f:
    manifest = json.load(f)
two_sided = set(manifest.get('two_sided_materials', []))

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


# ---------------------------------------------------------------- texture sets from the manifest
sets = {}  # material name -> (bc, normal_dx, rough) png basenames
for prop in manifest['props']:
    for mname, files in prop.get('materials', {}).items():
        bc, n, r = files
        sets[mname] = (bc, n.replace('_N.png', '_N_DX.png'), r)
# The manifest lists the ClanA ship materials only; the ClanB hull/sail use the same sets with ClanB colour maps.
for mname in list(sets):
    if 'ClanA' in mname:
        bc, n, r = sets[mname]
        other = mname.replace('ClanA', 'ClanB')
        if other not in sets and os.path.exists(os.path.join(SRC, bc.replace('ClanA', 'ClanB'))):
            sets[other] = (bc.replace('ClanA', 'ClanB'), n, r)

textures = {}
def texture(png, kind):
    name = os.path.splitext(png)[0]
    if name in textures:
        return textures[name]
    t = run_import(os.path.join(SRC, png), TEX, name)
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

for mname, (bc, n, r) in sets.items():
    texture(bc, 'bc'); texture(n, 'normal'); texture(r, 'rough')
log('imported %d textures for %d texture sets' % (len(textures), len(sets)))


# ---------------------------------------------------------------- master materials
def make_master(name, is_two_sided, sample):
    m = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property('two_sided', is_two_sided)
    bc_s, n_s, r_s = sample

    def tex_param(pname, tex, sampler, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -700, y)
        e.set_editor_property('parameter_name', pname)
        e.set_editor_property('texture', tex)
        e.set_editor_property('sampler_type', sampler)
        return e

    def scalar(pname, v, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -700, y)
        e.set_editor_property('parameter_name', pname)
        e.set_editor_property('default_value', v)
        return e

    bc = tex_param('BaseColor', bc_s, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, 0)
    nrm = tex_param('Normal', n_s, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, 300)
    rough = tex_param('Roughness', r_s, unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE, 600)
    tint = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -700, -250)
    tint.set_editor_property('parameter_name', 'Tint')
    tint.set_editor_property('default_value', unreal.LinearColor(1, 1, 1, 1))
    bright = scalar('Brightness', 1.0, -350)
    mul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, 0)
    mel.connect_material_expressions(bc, 'RGB', mul, 'A')
    mel.connect_material_expressions(tint, '', mul, 'B')
    mul2 = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -200, 0)
    mel.connect_material_expressions(mul, '', mul2, 'A')
    mel.connect_material_expressions(bright, '', mul2, 'B')
    mel.connect_material_property(mul2, '', MP.MP_BASE_COLOR)
    mel.connect_material_property(nrm, 'RGB', MP.MP_NORMAL)
    rmul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, 600)
    mel.connect_material_expressions(rough, 'R', rmul, 'A')
    mel.connect_material_expressions(scalar('RoughnessScale', 1.0, 750), '', rmul, 'B')
    rsat = mel.create_material_expression(m, unreal.MaterialExpressionSaturate, -200, 600)
    mel.connect_material_expressions(rmul, '', rsat, '')
    mel.connect_material_property(rsat, '', MP.MP_ROUGHNESS)
    mel.connect_material_property(scalar('Metallic', 0.0, 900), '', MP.MP_METALLIC)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m

sample = sets['M_Wood']
sample_tex = (textures[os.path.splitext(sample[0])[0]], textures[os.path.splitext(sample[1])[0]], textures[os.path.splitext(sample[2])[0]])
master = make_master('M_VikingKit', False, sample_tex)
master_two = make_master('M_VikingKit_TwoSided', True, sample_tex)

instances = {}
for mname, (bc, n, r) in sets.items():
    mi = tools.create_asset('MI_' + mname[2:] if mname.startswith('M_') else 'MI_' + mname, MAT,
                            unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property('parent', master_two if mname in two_sided else master)
    for pname, png in (('BaseColor', bc), ('Normal', n), ('Roughness', r)):
        mel.set_material_instance_texture_parameter_value(mi, pname, textures[os.path.splitext(png)[0]])
    mel.set_material_instance_scalar_parameter_value(mi, 'Metallic', METALLIC.get(mname, 0.0))
    if mname in TINT:
        mel.set_material_instance_vector_parameter_value(mi, 'Tint', unreal.LinearColor(*TINT[mname], 1.0))
    eal.save_loaded_asset(mi)
    instances[mname] = mi
log('created %d material instances' % len(instances))


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

fbx_files = sorted(f for f in os.listdir(SRC) if f.lower().endswith('.fbx'))
for fbx in fbx_files:
    name = os.path.splitext(fbx)[0]
    mesh = run_import(os.path.join(SRC, fbx), MESH, name, fbx_options())
    # Materials by slot name (the FBX keeps the Blender material names, e.g. M_Wood).
    missing = []
    for i, slot in enumerate(mesh.static_materials):
        sname = str(slot.material_slot_name)
        key = sname if sname in instances else next((k for k in sorted(instances, key=len, reverse=True) if sname.startswith(k)), None)
        if key:
            mesh.set_material(i, instances[key])
        else:
            missing.append(sname)
    nanite = mesh.get_editor_property('nanite_settings')
    nanite.set_editor_property('enabled', True)
    mesh.set_editor_property('nanite_settings', nanite)
    if name in COLLIDE:
        # (the StaticMeshEditorSubsystem replacement is not available inside the commandlet)
        unreal.EditorStaticMeshLibrary.add_simple_collisions(mesh, unreal.ScriptCollisionShapeType.BOX)
    eal.save_loaded_asset(mesh)
    b = mesh.get_bounding_box()
    log('%s slots=%d missing=%s bbox_min=(%.0f,%.0f,%.0f) bbox_max=(%.0f,%.0f,%.0f) tris=%d' % (
        name, len(mesh.static_materials), missing, b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z, mesh.get_num_triangles(0)))

unreal.log('WORLD_KIT_IMPORTED')
