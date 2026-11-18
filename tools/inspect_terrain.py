import unreal
m = unreal.load_asset('/Game/DragonRider/Opening/SM_FjordTerrain')
ns = m.get_editor_property('nanite_settings')
unreal.log_warning('INSPECT nanite=%s lods=%d tris0=%d bounds=%s' % (ns.get_editor_property('enabled'), m.get_num_lods(), m.get_num_triangles(0), m.get_bounds().box_extent))
for p in ('fallback_percent_triangles', 'fallback_relative_error', 'keep_percent_triangles', 'fallback_target'):
    try: unreal.log_warning('INSPECT %s=%s' % (p, ns.get_editor_property(p)))
    except Exception: pass
