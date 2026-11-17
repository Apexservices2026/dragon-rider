import unreal
bp = unreal.load_asset('/Game/DragonRider/BP_FlightPrototype')
cdo = unreal.get_default_object(bp.generated_class())
move = cdo.get_movement_component()
assert move.get_editor_property('max_speed') == 2400.0
assert move.get_editor_property('acceleration') == 1400.0
assert move.get_editor_property('deceleration') == 950.0
mode = unreal.load_asset('/Game/DragonRider/BP_FlightPrototypeMode')
assert unreal.get_default_object(mode.generated_class()).get_editor_property('default_pawn_class') == bp.generated_class()
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level('/Game/DragonRider/Lvl_FlightPrototype')
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world.get_world_settings().get_editor_property('default_game_mode') == mode.generated_class()
actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(bp.generated_class(), unreal.Vector(0,0,3000))
boom = actor.get_component_by_class(unreal.SpringArmComponent)
cam = actor.get_component_by_class(unreal.CameraComponent)
assert boom and cam
assert cam.get_attach_parent() == boom
assert boom.get_editor_property('target_arm_length') == 650.0
assert cam.get_editor_property('field_of_view') == 85.0
unreal.log('FLIGHT_PROTOTYPE_VALIDATED: persisted movement, mode, camera attachment, map')
# Inspection world is deliberately not saved.
