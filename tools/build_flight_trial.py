"""Create a readable flight-course presentation, preserving the original maps."""
import math
import unreal
P = '/Game/DragonRider'
DEST = P + '/Lvl_FlightTrial'
if unreal.EditorAssetLibrary.does_asset_exist(DEST):
    raise RuntimeError('Preserving existing trial level')
tools = unreal.AssetToolsHelpers.get_asset_tools()
def material(name, color, glow=0.0):
    path = P + '/' + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        raise RuntimeError('Preserving existing material: ' + name)
    mat = tools.create_asset(name, P, unreal.Material, unreal.MaterialFactoryNew())
    node = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
    node.set_editor_property('constant', unreal.LinearColor(*color))
    unreal.MaterialEditingLibrary.connect_material_property(node, '', unreal.MaterialProperty.MP_BASE_COLOR)
    if glow:
        emit = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
        emit.set_editor_property('constant', unreal.LinearColor(color[0]*glow,color[1]*glow,color[2]*glow,1))
        unreal.MaterialEditingLibrary.connect_material_property(emit, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    rough = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant)
    rough.set_editor_property('r', 0.75)
    unreal.MaterialEditingLibrary.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat
stone = material('M_TrialSlate',(0.055,0.075,0.10,1))
gold = material('M_TrialAmber',(0.8,0.34,0.035,1),1.5)
frost = material('M_TrialFrost',(0.08,0.55,0.7,1),1.2)
assert unreal.EditorAssetLibrary.duplicate_asset(P + '/Lvl_FlightPrototype', DEST)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level(DEST)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for actor in actors.get_all_level_actors():
    if isinstance(actor, unreal.StaticMeshActor):
        label = actor.get_actor_label()
        actor.static_mesh_component.set_material(0, gold if label.startswith('Pass ') else stone)
cube = unreal.load_asset('/Engine/BasicShapes/Cube')
def block(name, location, scale, mat, yaw=0):
    actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*location),unreal.Rotator(yaw=yaw))
    actor.set_actor_label(name)
    actor.set_folder_path('Trial Presentation')
    actor.static_mesh_component.set_static_mesh(cube)
    actor.static_mesh_component.set_material(0,mat)
    actor.set_actor_scale3d(unreal.Vector(*scale))
    return actor
def label(name,text,location,size,yaw=180):
    actor=actors.spawn_actor_from_class(unreal.TextRenderActor,unreal.Vector(*location),unreal.Rotator(yaw=yaw))
    actor.set_actor_label(name)
    actor.set_folder_path('Trial Presentation')
    comp=actor.get_component_by_class(unreal.TextRenderComponent)
    comp.set_text(unreal.Text(text))
    comp.set_world_size(size)
    comp.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    comp.set_text_render_color(unreal.Color(225,240,255,255))
route=[(2400,0,3000),(5300,0,3850),(7900,1200,4700),(9600,3700,4750),(9750,6500,3350),(8900,9200,2200)]
previous=(0,0,3000)
for i,point in enumerate(route,1):
    x,y,z=point
    heading=math.degrees(math.atan2(y-previous[1],x-previous[0]))
    label('Gate label %02d'%i,'%02d / 06'%i,(x-30,y,z+680),130,heading+180)
    # Narrow markers connect successive gates without obstructing the flying corridor.
    for j in range(1,6):
        t=j/6
        px=previous[0]+(x-previous[0])*t
        py=previous[1]+(y-previous[1])*t
        pz=previous[2]+(z-previous[2])*t-600
        block('Route %02d marker %02d'%(i,j),(px,py,pz),(0.6,2.4,0.6),frost,heading)
    previous=point
label('Title','DRAGON RIDER',(2000,0,4400),190)
label('Trial subtitle','FLIGHT TRIAL',(1990,0,4140),100)
label('Controls','MOUSE - STEER   |   W A S D - MOVE',(1600,0,1800),65)
label('Altitude controls','SPACE - CLIMB   |   CTRL - DESCEND',(1600,0,1680),65)
label('Finish','END OF COURSE',(8650,9900,3100),140,290)
assert levels.save_current_level()
unreal.log('FLIGHT_TRIAL_PRESENTATION_SAVED')
