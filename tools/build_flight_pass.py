import math
import unreal

DEST = "/Game/DragonRider/Lvl_FlightPass"
if unreal.EditorAssetLibrary.does_asset_exist(DEST):
    raise RuntimeError("Flight course already exists; preserving it.")

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not levels.new_level_from_template(DEST, "/Engine/Maps/Templates/Template_Default"):
    raise RuntimeError("Could not create flight course")

cube = unreal.load_asset("/Engine/BasicShapes/Cube")
if not cube:
    raise RuntimeError("Engine cube missing")
def block(label, position, scale, angle=0):
    actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*position), unreal.Rotator(yaw=angle))
    actor.set_actor_label(label)
    actor.set_folder_path("Flight Pass")
    actor.static_mesh_component.set_static_mesh(cube)
    actor.set_actor_scale3d(unreal.Vector(*scale))
    return actor

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
world.get_world_settings().set_editor_property("default_game_mode", unreal.GameModeBase)
mode = unreal.get_default_object(unreal.GameModeBase)
pawn = mode.get_editor_property("default_pawn_class")
if pawn != unreal.DefaultPawn.static_class():
    raise RuntimeError("Unexpected default pawn: " + str(pawn))

starts = [actor for actor in actors.get_all_level_actors() if isinstance(actor, unreal.PlayerStart)]
start = starts[0] if starts else actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 3000))
if len(starts) > 1:
    raise RuntimeError("Ambiguous template start")
start.set_actor_location_and_rotation(unreal.Vector(0, 0, 3000), unreal.Rotator(), False, True)
start.set_actor_label("Flight Pass Start")

# Heights are the centers of the openings. Each gate faces the arriving player.
route = [(2400, 0, 3000), (5300, 0, 3850), (7900, 1200, 4700),
         (9600, 3700, 4750), (9750, 6500, 3350), (8900, 9200, 2200)]
previous = (0, 0, 3000)
for index, (x, y, z) in enumerate(route, 1):
    heading = math.atan2(y - previous[1], x - previous[0])
    across = (-math.sin(heading), math.cos(heading))
    name = "Pass %02d" % index
    for side in (-1, 1):
        block(name + (" Left" if side < 0 else " Right"),
              (x + across[0]*570*side, y + across[1]*570*side, z),
              (1.2, 1.2, 9.2), math.degrees(heading))
    block(name + " Lintel", (x, y, z+490), (1.2, 12.6, 0.8), math.degrees(heading))
    block(name + " Sill", (x, y, z-490), (1.2, 12.6, 0.8), math.degrees(heading))
    previous = (x, y, z)

block("Valley Floor", (4800, 4500, -160), (190, 190, 2))
if not levels.save_current_level():
    raise RuntimeError("Course save failed")
unreal.log("DRAGON_RIDER_FLIGHT_PASS_SAVED: six gates, native flying pawn")
