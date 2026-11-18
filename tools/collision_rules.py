"""Simple-collision rules for the world kit and the island landmark kit, and an in-place fixer.

Used by tools/import_world_kit.py and tools/import_landmarks.py after import. Run on its own to (re)apply the rules
to the already-imported meshes without reimporting anything:
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Collision is set through the C++ helper UDragonAssetLibrary.SetCollision (DragonRiderEditor): the Python
StaticMeshEditorSubsystem / EditorStaticMeshLibrary collision calls silently do nothing inside a commandlet,
which left every kit and landmark mesh without collision until this fix.

  box   - one bounding box: buildings, walls, wrecks, piers
  kdop  - one tight 26-sided hull: rocks, crystals, boulders, runestones, altar, driftwood
  int   - convex decomposition into that many hulls: open or hollow shapes (the shrine arch and the plunge-rock ring
          stay open, the ribcage and nest keep their outline)
Meshes not listed (sails, oars, banners, small props, the waterfall sheet and foam) get none.
"""
import unreal

KIT = {n: 'box' for n in ('SM_Longhouse', 'SM_Hut', 'SM_Storehouse', 'SM_Smithy', 'SM_PierSection', 'SM_PierEnd',
                          'SM_PalisadeWall', 'SM_PalisadeGate', 'SM_Watchtower')}
LANDMARKS = {
    'SM_MeadHall': 'box', 'SM_Gatehouse': 'box', 'SM_FortWall': 'box', 'SM_FortWallCurve15': 'box', 'SM_BeaconTower': 'box',
    'SM_WreckBow': 'box', 'SM_WreckStern': 'box',
    'SM_EmberCrystals': 'kdop', 'SM_LavaRock_A': 'kdop', 'SM_LavaRock_B': 'kdop', 'SM_LavaRock_C': 'kdop',
    'SM_FrostBoulder_A': 'kdop', 'SM_FrostBoulder_B': 'kdop', 'SM_FrostBoulder_C': 'kdop', 'SM_RuneAltar': 'kdop',
    'SM_Runestone_A': 'kdop', 'SM_Runestone_B': 'kdop', 'SM_Runestone_C': 'kdop', 'SM_Runestone_D': 'kdop',
    'SM_DriftwoodPile': 'kdop',
    'SM_RuneCircle': 16, 'SM_IceShrine': 10, 'SM_DragonRibs': 12, 'SM_DragonSkull': 6, 'SM_DragonNest': 8,
    'SM_FallsLip': 6, 'SM_PlungeRocks': 14, 'SM_ObsidianSpires_A': 6, 'SM_ObsidianSpires_B': 5,
}
RULES = dict(KIT, **LANDMARKS)


def apply(mesh):
    """Apply the rule for this mesh (by asset name). Returns (rule, primitive count) or (None, 0)."""
    kind = RULES.get(mesh.get_name())
    if not kind:
        return None, 0
    if isinstance(kind, int):
        n = unreal.DragonAssetLibrary.set_collision(mesh, 'hulls', kind, 16)
    else:
        n = unreal.DragonAssetLibrary.set_collision(mesh, kind, 1, 16)
    body = mesh.get_editor_property('body_setup')
    if body:
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    return kind, n


if __name__ == '__main__':
    eal = unreal.EditorAssetLibrary
    for folder in ('/Game/DragonRider/World/Meshes', '/Game/DragonRider/World/Landmarks/Meshes'):
        for path in eal.list_assets(folder, recursive=False):
            m = eal.load_asset(path)
            if isinstance(m, unreal.StaticMesh):
                kind, n = apply(m)
                if kind:
                    eal.save_loaded_asset(m, False)
                    unreal.log('COLLISION_RULES: %s %s -> %d primitives' % (m.get_name(), kind, n))
