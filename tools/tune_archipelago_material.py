"""In-place tweaks to the archipelago landscape material, without rebuilding the level or the landscapes.

Run headless:
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
tools/build_archipelago.py builds the same thing from scratch, so the two stay in step.

- Specular / roughness: looking toward the low golden-hour sun, sunlit grass on the forest isle's ridges glared as
  cream bands (grazing-angle reflection). A 'Specular' parameter (0.15) and 'RoughnessToOne' (0.75: blends the
  layer roughness toward fully rough) remove it.
- Lava crust: the lava lake's crack noise was 9 m grain, which read as a speckled disc; 0.00025 gives ~40 m crust
  plates with glowing cracks between them.
"""
import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
m = eal.load_asset('/Game/DragonRider/Archipelago/M_ArchipelagoLand')
if not m:
    raise RuntimeError('M_ArchipelagoLand missing - run tools/build_archipelago.py')
if 'Specular' not in [str(n) for n in mel.get_scalar_parameter_names(m)]:
    e = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -400, 1700)
    e.set_editor_property('parameter_name', 'Specular')
    e.set_editor_property('default_value', 0.15)
    e.set_editor_property('group', 'Layers')
    mel.connect_material_property(e, '', unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    unreal.log('TUNE_MATERIAL: added Specular 0.15 to M_ArchipelagoLand')
else:
    unreal.log('TUNE_MATERIAL: already tuned')

if 'RoughnessToOne' not in [str(n) for n in mel.get_scalar_parameter_names(m)]:
    rough_in = mel.get_material_property_input_node(m, unreal.MaterialProperty.MP_ROUGHNESS)
    p = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -400, 1800)
    p.set_editor_property('parameter_name', 'RoughnessToOne')
    p.set_editor_property('default_value', 0.75)
    p.set_editor_property('group', 'Layers')
    one = mel.create_material_expression(m, unreal.MaterialExpressionConstant, -400, 1900)
    one.set_editor_property('r', 1.0)
    lerp = mel.create_material_expression(m, unreal.MaterialExpressionLinearInterpolate, -200, 1800)
    mel.connect_material_expressions(rough_in, '', lerp, 'A')
    mel.connect_material_expressions(one, '', lerp, 'B')
    mel.connect_material_expressions(p, '', lerp, 'Alpha')
    mel.connect_material_property(lerp, '', unreal.MaterialProperty.MP_ROUGHNESS)
    unreal.log('TUNE_MATERIAL: roughness blended toward 1')

# Lava crack noise: walk back from the emissive output to the Noise node(s) and enlarge the grain.
seen, stack, changed = set(), [mel.get_material_property_input_node(m, unreal.MaterialProperty.MP_EMISSIVE_COLOR)], 0
while stack:
    e = stack.pop()
    if e is None or e.get_name() in seen:
        continue
    seen.add(e.get_name())
    if isinstance(e, unreal.MaterialExpressionNoise) and abs(e.get_editor_property('scale') - 0.00025) > 1e-7:
        e.set_editor_property('scale', 0.00025)
        e.set_editor_property('levels', 5)
        changed += 1
    stack.extend(mel.get_inputs_for_material_expression(m, e))
mel.recompile_material(m)
eal.save_loaded_asset(m)
unreal.log('TUNE_MATERIAL: lava noise nodes changed: %d' % changed)

# Lighting: looking toward the low sun, the volumetric fog lit by the sun drew bright cream bands over every
# sunlit slope (the light shafts follow the terrain shadows). Softer sun scattering in the fog removes them.
# Saves only the Sun and Fog actor packages (same values as tools/build_archipelago.py).
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels.load_level('/Game/DragonRider/Archipelago/Lvl_Archipelago')
pkgs = []
for a in actors.get_all_level_actors():
    if a.get_actor_label() == 'Sun':
        a.light_component.set_editor_property('volumetric_scattering_intensity', 0.35)
        # The cream bands on sunlit ridges seen toward the low sun are the sun's specular highlight at grazing angles
        # (they vanish with ShowFlag.Specular 0 and nothing else: not the albedo, fog, atmosphere, skylight or Lumen).
        # Fresnel drives grazing specular toward 1 whatever the material's Specular, so tone the sun's specular down.
        a.light_component.set_editor_property('specular_scale', 0.3)
        pkgs.append(a.get_package())
    elif a.get_actor_label() == 'Fog':
        a.component.set_editor_property('directional_inscattering_luminance', unreal.LinearColor(0.45, 0.32, 0.2, 1))
        pkgs.append(a.get_package())
if pkgs:
    unreal.EditorLoadingAndSavingUtils.save_packages(pkgs, False)
unreal.log('TUNE_MATERIAL: softened sun scattering in the fog (%d actors)' % len(pkgs))
