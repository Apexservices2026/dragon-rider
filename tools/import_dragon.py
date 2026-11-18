"""Import Vertex's rigged dragon and Viking rider into /Game/DragonRider/Characters.

Run headless (rebuilds everything under /Game/DragonRider/Characters; nothing else is touched):
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Requires Saved/Generated/Dragon/{Dragon,Rider}.fbx and Textures/*.png from tools/blender/dragon/*.py.

Creates SK_Dragon + SK_Rider (each with its own skeleton), one AnimSequence per FBX take
(Flap, Glide, DiveTuck, WingBeatStrong, Hover / RiderIdle) and materials from the texture sets:
BaseColor (sRGB), Normal_DX, ORM (R AO, G roughness, B metallic) and Emissive x EmissiveStrength.
Wing membranes get the two-sided master. The pawn attaches the rider to the dragon's Saddle bone.
"""
import os
import unreal

ROOT = '/Game/DragonRider/Characters'
TEX = ROOT + '/Textures'
MAT = ROOT + '/Materials'
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SRC = os.path.join(PROJECT_DIR, 'Saved', 'Generated', 'Dragon')

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty

# texture set -> (emissive strength, emissive tint)
SETS = {
    'T_Dragon_Body': (4.0, (1.0, 0.45, 0.12)),
    'T_Dragon_Wings': (3.5, (1.0, 0.42, 0.1)),    # ember-orange veins (higher saturates the whole membrane in sun)
    'T_Rider': (2.0, (1.0, 0.8, 0.6)),
}


def log(msg):
    unreal.log('DRAGON_IMPORT: ' + msg)


if eal.does_directory_exist(ROOT):
    eal.delete_directory(ROOT)
for d in (ROOT, TEX, MAT):
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
    return task.get_editor_property('imported_object_paths')


# ---------------------------------------------------------------- textures
textures = {}
for base in SETS:
    for suffix, kind in (('_BaseColor', 'bc'), ('_Normal_DX', 'n'), ('_ORM', 'orm'), ('_Emissive', 'e')):
        name = base + suffix
        run_import(os.path.join(SRC, 'Textures', name + '.png'), TEX, name)
        t = eal.load_asset(TEX + '/' + name)
        if not t:
            raise RuntimeError('Texture import failed: ' + name)
        if kind == 'n':
            t.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
            t.set_editor_property('srgb', False)
        elif kind == 'orm':
            t.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_MASKS)
            t.set_editor_property('srgb', False)
        else:
            t.set_editor_property('srgb', True)
        eal.save_loaded_asset(t)
        textures[name] = t
log('imported %d textures' % len(textures))


# ---------------------------------------------------------------- materials
def make_master(name, two_sided):
    m = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property('two_sided', two_sided)
    m.set_editor_property('used_with_skeletal_mesh', True)
    def tp(pname, tex, sampler, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -900, y)
        e.set_editor_property('parameter_name', pname)
        e.set_editor_property('texture', tex)
        e.set_editor_property('sampler_type', sampler)
        return e
    def sp(pname, v, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -900, y)
        e.set_editor_property('parameter_name', pname)
        e.set_editor_property('default_value', v)
        return e
    def vp(pname, c, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -900, y)
        e.set_editor_property('parameter_name', pname)
        e.set_editor_property('default_value', unreal.LinearColor(c[0], c[1], c[2], 1))
        return e
    def mul(a, ao, b, bo, x, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, x, y)
        mel.connect_material_expressions(a, ao, e, 'A')
        mel.connect_material_expressions(b, bo, e, 'B')
        return e
    S = unreal.MaterialSamplerType
    bc = tp('BaseColor', textures['T_Dragon_Body_BaseColor'], S.SAMPLERTYPE_COLOR, 0)
    n = tp('Normal', textures['T_Dragon_Body_Normal_DX'], S.SAMPLERTYPE_NORMAL, 300)
    orm = tp('ORM', textures['T_Dragon_Body_ORM'], S.SAMPLERTYPE_MASKS, 600)
    em = tp('Emissive', textures['T_Dragon_Body_Emissive'], S.SAMPLERTYPE_COLOR, 900)
    tint = vp('Tint', (1, 1, 1), -200)
    bcol = mul(bc, 'RGB', tint, '', -600, 0)
    mel.connect_material_property(mul(bcol, '', sp('Brightness', 1.0, -100), '', -400, 0), '', MP.MP_BASE_COLOR)
    mel.connect_material_property(n, 'RGB', MP.MP_NORMAL)
    mel.connect_material_property(orm, 'R', MP.MP_AMBIENT_OCCLUSION)
    rough = mul(orm, 'G', sp('RoughnessScale', 1.0, 700), '', -600, 650)
    rs = mel.create_material_expression(m, unreal.MaterialExpressionSaturate, -400, 650)
    mel.connect_material_expressions(rough, '', rs, '')
    mel.connect_material_property(rs, '', MP.MP_ROUGHNESS)
    mel.connect_material_property(mul(orm, 'B', sp('MetallicScale', 1.0, 800), '', -600, 750), '', MP.MP_METALLIC)
    e1 = mul(em, 'RGB', vp('EmissiveTint', (1, 0.45, 0.12), 1000), '', -600, 900)
    mel.connect_material_property(mul(e1, '', sp('EmissiveStrength', 6.0, 1100), '', -400, 900), '', MP.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m

master = make_master('M_Creature', False)
master_two = make_master('M_Creature_TwoSided', True)

mis = {}
for base, (strength, tint) in SETS.items():
    short = base[2:]
    for variant, parent in (('', master), ('_TwoSided', master_two)):
        if variant and base != 'T_Dragon_Wings':
            continue
        mi = tools.create_asset('MI_' + short + variant, MAT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mi.set_editor_property('parent', parent)
        mel.set_material_instance_texture_parameter_value(mi, 'BaseColor', textures[base + '_BaseColor'])
        mel.set_material_instance_texture_parameter_value(mi, 'Normal', textures[base + '_Normal_DX'])
        mel.set_material_instance_texture_parameter_value(mi, 'ORM', textures[base + '_ORM'])
        mel.set_material_instance_texture_parameter_value(mi, 'Emissive', textures[base + '_Emissive'])
        mel.set_material_instance_scalar_parameter_value(mi, 'EmissiveStrength', strength)
        mel.set_material_instance_vector_parameter_value(mi, 'EmissiveTint', unreal.LinearColor(tint[0], tint[1], tint[2], 1))
        eal.save_loaded_asset(mi)
        mis[short + variant] = mi
log('materials: %s' % sorted(mis))


def pick_material(slot_name):
    s = slot_name.lower()
    if 'wing' in s or 'membrane' in s:
        return mis['Dragon_Wings_TwoSided']
    if 'rider' in s or 'viking' in s or 'cloth' in s or 'leather' in s or 'skin' in s:
        return mis['Rider']
    return mis['Dragon_Body']


# ---------------------------------------------------------------- skeletal meshes + animations
def fbx_skeletal():
    ui = unreal.FbxImportUI()
    ui.import_mesh = True
    ui.import_as_skeletal = True
    ui.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    ui.import_materials = False
    ui.import_textures = False
    ui.import_animations = True
    ui.create_physics_asset = False
    sk = ui.skeletal_mesh_import_data
    sk.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
    sk.set_editor_property('import_morph_targets', False)
    ad = ui.anim_sequence_import_data
    ad.set_editor_property('animation_length', unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    ad.set_editor_property('import_bone_tracks', True)
    return ui


for fbx, name, default_mi in (('Dragon.fbx', 'SK_Dragon', 'Dragon_Body'), ('Rider.fbx', 'SK_Rider', 'Rider')):
    paths = run_import(os.path.join(SRC, fbx), ROOT, name, fbx_skeletal())
    mesh = eal.load_asset(ROOT + '/' + name)
    if not mesh:
        raise RuntimeError('Skeletal import failed for %s; got %s' % (fbx, paths))
    mats = mesh.get_editor_property('materials')
    for sm in mats:
        slot = str(sm.get_editor_property('material_slot_name'))
        mi = pick_material(slot) if name == 'SK_Dragon' else mis['Rider']
        sm.set_editor_property('material_interface', mi)
        log('%s slot %s -> %s' % (name, slot, mi.get_name()))
    mesh.set_editor_property('materials', mats)
    eal.save_loaded_asset(mesh)
    b = mesh.get_bounds()
    skel = mesh.get_editor_property('skeleton')
    log('%s bounds origin=%s extent=%s skeleton=%s' % (name, b.origin, b.box_extent, skel.get_name() if skel else None))
    for p in paths or []:
        log('  imported ' + str(p))

# Animations keep the importer's names: SK_DragonDragonRig_<Take> and SK_Rider_Anim (the pawn loads these at runtime).
for p in eal.list_assets(ROOT, recursive=False):
    a = eal.find_asset_data(p)
    log('asset %s (%s)' % (p, a.asset_class_path.asset_name))
    if str(a.asset_class_path.asset_name) == 'AnimSequence':
        seq = eal.load_asset(p)
        try:
            log('   length %.2fs skeleton=%s' % (seq.get_play_length(), seq.get_editor_property('skeleton').get_name()))
        except Exception as e:
            log('   (length unavailable: %s)' % e)

# Re-apply the materials after the (Interchange) import has fully finished, then save everything.
for name in ('SK_Dragon', 'SK_Rider'):
    mesh = eal.load_asset(ROOT + '/' + name)
    mats = mesh.get_editor_property('materials')
    for sm in mats:
        slot = str(sm.get_editor_property('material_slot_name'))
        sm.set_editor_property('material_interface', pick_material(slot) if name == 'SK_Dragon' else mis['Rider'])
    mesh.set_editor_property('materials', mats)
    mesh.modify()
    eal.save_loaded_asset(mesh, only_if_is_dirty=False)
eal.save_directory(ROOT, only_if_is_dirty=False, recursive=True)  # skeletons included (import tasks don't save)
# Drop the machine-specific source paths Interchange stores in the import data (tools/scrub_import_paths.py).
import sys as _sys
_sys.path.insert(0, os.path.normpath(os.path.join(PROJECT_DIR, '..', '..', 'tools')))
import scrub_import_paths
scrub_import_paths.scrub_folders([ROOT])
unreal.log('DRAGON_IMPORT_DONE')
