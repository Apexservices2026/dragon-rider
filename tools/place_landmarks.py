"""Place Vertex's island landmark kit on the archipelago (Lvl_Archipelago).

Run headless after tools/import_landmarks.py and tools/terrain/pick_landmark_sites.py:
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>" -AllowCommandletRendering
Rerunnable: deletes and recreates only actors in the Archipelago/Landmarks/* folders (landmarks + their review
legs). It never touches the landscapes, so a rerun writes only these few small actor packages.

- Forest isle: ring-fort (straight FortWall segments on a 38 m circle; the pre-bent 30.6 m ring is too tight for
  the 52 m mead hall), gatehouse in the gap facing the sea, mead hall in the middle along the contour, porch to
  the gate. Waterfall: lip rock at the gorge crest, the water sheet tilted down the cliff face to the plunge
  pool, plunge rocks and foam at the bottom.
- Glacier isle: rune circle (with its altar) on a flat shoulder, a runestone path up to the ice shrine on the
  ice field, frost boulders.
- Ember isle: the dragon lair on the caldera floor beside the lava lake (nest with eggs, skull, ribs, obsidian
  spires, ember crystals, lava rocks).
- Every island: shipwreck halves and driftwood on beaches, beacon towers on headlands (landmarks.json "coast").
Grounding: each piece sits at the lowest ground under its footprint (never floats); the uphill burial is logged.
"""
import json
import math
import os
import random
import re
import sys
import unreal

LEVEL = '/Game/DragonRider/Archipelago/Lvl_Archipelago'
KIT = '/Game/DragonRider/World/Landmarks/Meshes/'
FOLDER = 'Archipelago/Landmarks'
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
GEN = os.path.join(PROJECT_DIR, 'Saved', 'Generated', 'Archipelago')
TOOLS = os.path.normpath(os.path.join(PROJECT_DIR, '..', '..', 'tools'))
sys.path.insert(0, TOOLS)
import archipelago_heights  # noqa: E402

SITES = json.load(open(os.path.join(GEN, 'landmarks.json')))
ARCH = archipelago_heights.Archipelago(GEN)
height, footprint = ARCH.height, ARCH.footprint

eal = unreal.EditorAssetLibrary
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rng = random.Random(2026)


def log(msg):
    unreal.log('PLACE_LANDMARKS: ' + msg)


world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not world or world.get_path_name().split('.')[0] != LEVEL:
    levels.load_level(LEVEL)
OWN_LABELS = re.compile(r'^(Stronghold_|Waterfall_|Glacier_|Lair_|Coast_)|^Review_\d+_(stronghold|stronghold_hall|waterfall|'
                        r'rune_circle|ice_shrine|dragon_lair|(main|forest|glacier|ember)_(wreck|beacon|driftwood))$')
removed = []
for a in actors.get_all_level_actors():
    tags = [str(t) for t in a.get_editor_property('tags')]
    if str(a.get_folder_path()).startswith(FOLDER) or 'DR_Landmark' in tags or OWN_LABELS.match(a.get_actor_label()):
        removed.append(a.get_package())
        actors.destroy_actor(a)
log('removed %d previous landmark actors' % len(removed))

meshes = {}
def mesh(name):
    if name not in meshes:
        meshes[name] = eal.load_asset('/Engine/BasicShapes/Cube' if name == 'Cube' else KIT + name)
        if not meshes[name]:
            raise RuntimeError('Missing landmark mesh %s - run tools/import_landmarks.py first' % name)
    return meshes[name]


placed = []
def place(name, x, y, z, yaw, group, label, pitch=0.0, scale=(1.0, 1.0, 1.0), collide=True):
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
    a.static_mesh_component.set_static_mesh(mesh(name))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER + '/' + group)
    a.set_editor_property('is_spatially_loaded', False)
    a.set_editor_property('tags', [unreal.Name('DR_Landmark')])
    if scale != (1.0, 1.0, 1.0):
        a.set_actor_scale3d(unreal.Vector(*scale))
    if not collide:
        a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    placed.append(a)
    return a


def grounded(name, x, y, yaw, hx, hy, group, label, sink=0.0, n=3, lift=0.0, **kw):
    """Place at the lowest footprint height (minus sink cm), raised by lift x the footprint's height range (big
    pieces use ~0.3 so the uphill side isn't swallowed; their base skirts hide the small gap downhill).
    Returns (actor, uphill burial cm)."""
    fp = footprint(x, y, yaw, hx, hy, n)
    lo, hi = min(fp), max(fp)
    z = lo + lift * (hi - lo) - sink
    return place(name, x, y, z, yaw, group, label, **kw), hi - z


report = []
CUBE = eal.load_asset('/Engine/BasicShapes/Cube')
KIT_MAT = '/Game/DragonRider/World/Materials/'


def seated(name, x, y, yaw, hx, hy, group, label, plinth_mi, n=3, pad=60.0, top_below=0.0, **kw):
    """Seat a building at the UPHILL height of its footprint (nothing sinks into the slope) and fill the gap under
    the downhill side with a plinth: an earth or dry-stone block from just under the piece down into the ground.
    Returns (actor, height of the plinth's tallest side in cm)."""
    fp = footprint(x, y, yaw, hx, hy, n)
    lo, hi = min(fp), max(fp)
    z = hi - 20.0
    a = place(name, x, y, z, yaw, group, label, **kw)
    if hi - lo > 30.0:
        top = z - top_below
        bottom = lo - 100.0
        p = place('Cube', x, y, (top + bottom) / 2.0, yaw, group, label + '_Plinth',
                  scale=((2 * hx + pad) / 100.0, (2 * hy + pad) / 100.0, (top - bottom) / 100.0))
        p.static_mesh_component.set_material(0, eal.load_asset(KIT_MAT + plinth_mi))
    return a, hi - lo

# ---------------------------------------------------------------- forest: stronghold
st = SITES['stronghold']
cx, cy = st['x'] * 100.0, st['y'] * 100.0
g = st['gate_deg']
R = st['wall_radius_m'] * 100.0
n_seg = 30
walls, worst = 0, 0.0
for k in range(n_seg):
    a = g + (k + 0.5) * 360.0 / n_seg
    if abs((a - g + 180.0) % 360.0 - 180.0) < 12.0:
        continue  # gate gap
    x, y = cx + R * math.cos(math.radians(a)), cy + R * math.sin(math.radians(a))
    # the rampart's own earth bank reaches 1.26 m below its origin, so its plinth starts just under that
    _, b = seated('SM_FortWall', x, y, a - 90.0, 400, 520, 'Stronghold', 'Stronghold_Wall%02d' % k, 'MI_Turf', pad=0.0, top_below=110.0)
    worst = max(worst, b); walls += 1
gx, gy = cx + R * math.cos(math.radians(g)), cy + R * math.sin(math.radians(g))
_, b_gate = seated('SM_Gatehouse', gx, gy, g, 400, 755, 'Stronghold', 'Stronghold_Gatehouse', 'MI_Stone', pad=80.0)
hall_yaw = st.get('hall_yaw_deg', g)
if abs((hall_yaw - g + 180.0) % 360.0 - 180.0) > 90.0:
    hall_yaw += 180.0  # porch (+X) toward the gate
hall, b_hall = seated('SM_MeadHall', cx, cy, hall_yaw, 2600, 900, 'Stronghold', 'Stronghold_MeadHall', 'MI_Stone', n=5, pad=160.0)
hall.set_editor_property('tags', [unreal.Name('DR_Landmark'), unreal.Name('Landmark_Stronghold')])
report.append('stronghold at (%.0f, %.0f) m: %d wall segments (tallest plinth %.0f cm), gatehouse plinth %.0f cm, hall plinth %.0f cm; nothing sinks uphill' % (
    st['x'], st['y'], walls, worst, b_gate, b_hall))

# ---------------------------------------------------------------- forest: waterfall
wf = SITES['waterfall']
lx, ly, lz = wf['lip_x'] * 100.0, wf['lip_y'] * 100.0, wf['lip_z'] * 100.0
d = math.radians(wf['dir_deg'])
ux, uy = math.cos(d), math.sin(d)
def along(t):
    return lx + ux * t, ly + uy * t
prof = [(t, height(*along(t))) for t in range(-4000, 8000, 100)]
t_lip = max(t for t, z in prof if z > lz - 150.0 and t < 3000)
t_base = min(t for t, z in prof if z < 50.0 and t > t_lip)
drop = height(*along(t_lip)) - 0.0
run = t_base - t_lip
x, y = along(t_lip - 300)
place('SM_FallsLip', x, y, height(x, y) - 320.0, wf['dir_deg'], 'Waterfall', 'Waterfall_Lip')
# The sheet runs from the crest down the cliff face: base at the pool, leaning back toward the lip.
def clears(tb):
    for t in range(t_lip + 100, tb, 100):
        if drop * (tb - t) / float(tb - t_lip) < height(*along(t)) + 150.0:
            return False
    return True
t_sheet = next((tb for tb in range(t_base + 150, t_base + 6000, 100) if clears(tb)), t_base + 2000)
run = t_sheet - t_lip
length = math.hypot(drop, run)
pitch = math.degrees(math.atan2(run, drop))
x, y = along(t_sheet)
place('SM_WaterfallSheet', x, y, -60.0, wf['dir_deg'], 'Waterfall', 'Waterfall_Sheet', pitch=pitch,
      scale=(1.0, 1.6, length / 2415.0), collide=False)
# The stream: a sheet laid flat on the gorge floor for 40 m upstream of the lip (pitch 90 lays the sheet's long
# axis back upstream, face up), so there is water at the crest that pours over it; foam where it tips over.
fz = height(*along(t_lip - 200))
x, y = along(t_lip + 150)
place('SM_WaterfallSheet', x, y, fz + 40.0, wf['dir_deg'], 'Waterfall', 'Waterfall_Stream', pitch=88.0,
      scale=(1.0, 1.3, 4000.0 / 2415.0), collide=False)
x, y = along(t_lip + 100)
place('SM_WaterfallFoam', x, y, fz - 150.0, wf['dir_deg'], 'Waterfall', 'Waterfall_CrestFoam', scale=(0.45, 0.45, 0.45), collide=False)
x, y = along(t_sheet + 500)
place('SM_PlungeRocks', x, y, 0.0, wf['dir_deg'], 'Waterfall', 'Waterfall_PlungeRocks')
x, y = along(t_sheet + 150)
place('SM_WaterfallFoam', x, y, 0.0, wf['dir_deg'], 'Waterfall', 'Waterfall_Foam', collide=False)
report.append('waterfall: crest %.0f m at t=%.0f m, cliff foot t=%.0f m, sheet foot t=%.0f m, %.0f m long leaning %.0f deg' % (
    drop / 100.0, t_lip / 100.0, t_base / 100.0, t_sheet / 100.0, length / 100.0, pitch))

# ---------------------------------------------------------------- glacier: rune circle, runestone path, ice shrine
rc, sh = SITES['rune_circle'], SITES['ice_shrine']
rx, ry = rc['x'] * 100.0, rc['y'] * 100.0
sx, sy = sh['x'] * 100.0, sh['y'] * 100.0
path_yaw = math.degrees(math.atan2(sy - ry, sx - rx))
circle, b_c = grounded('SM_RuneCircle', rx, ry, path_yaw, 900, 900, 'Glacier', 'Glacier_RuneCircle', sink=20, n=4, lift=0.3)
circle.set_editor_property('tags', [unreal.Name('DR_Landmark'), unreal.Name('Landmark_RuneCircle')])
shrine, b_s = grounded('SM_IceShrine', sx, sy, sh.get('yaw_deg', path_yaw + 180.0), 140, 480, 'Glacier', 'Glacier_IceShrine', sink=30, lift=0.25)
dist = math.hypot(sx - rx, sy - ry)
for k, t in enumerate((0.12, 0.3, 0.5, 0.7, 0.88)):
    px = rx + (sx - rx) * t + rng.uniform(-600, 600)
    py = ry + (sy - ry) * t + rng.uniform(-600, 600)
    grounded('SM_Runestone_%s' % 'ABCD'[k % 4], px, py, path_yaw - 90.0 + rng.uniform(-10, 10), 80, 30,
             'Glacier', 'Glacier_Runestone%d' % k, sink=40)
for k in range(6):
    a = rng.uniform(0, 360); r = rng.uniform(1500, 3200)
    grounded('SM_FrostBoulder_%s' % 'ABC'[k % 3], rx + r * math.cos(math.radians(a)), ry + r * math.sin(math.radians(a)),
             rng.uniform(0, 360), 150, 120, 'Glacier', 'Glacier_Boulder%d' % k, sink=30)
report.append('rune circle at %.0f m (burial %.0f cm), ice shrine at %.0f m (burial %.0f cm), path %.0f m' % (
    rc['z'], b_c, sh['z'], b_s, dist / 100.0))

# ---------------------------------------------------------------- ember: dragon lair beside the lava lake
lr = SITES['lair']
px, py = lr['x'] * 100.0, lr['y'] * 100.0
face = lr['facing_deg']                       # toward the lake centre
fx, fy = math.cos(math.radians(face)), math.sin(math.radians(face))
sx_, sy_ = -fy, fx                            # sideways
def lair(name, fwd_m, side_m, yaw, hx, hy, label, sink=20.0, lift=0.15):
    return grounded(name, px + (fx * fwd_m + sx_ * side_m) * 100.0, py + (fy * fwd_m + sy_ * side_m) * 100.0, yaw, hx, hy,
                    'Lair', 'Lair_' + label, sink=sink, lift=lift)
nest, b_n = lair('SM_DragonNest', 0, 0, face, 1000, 1000, 'Nest', sink=30, lift=0.3)
nest.set_editor_property('tags', [unreal.Name('DR_Landmark'), unreal.Name('Landmark_Lair')])
lair('SM_DragonSkull', 14, -16, face + 140, 450, 130, 'Skull')
lair('SM_DragonRibs', -6, 22, face + 70, 800, 340, 'Ribs', sink=40)
lair('SM_ObsidianSpires_A', -38, -14, rng.uniform(0, 360), 380, 330, 'SpiresA', sink=40)
lair('SM_ObsidianSpires_B', -34, 20, rng.uniform(0, 360), 360, 330, 'SpiresB', sink=40)
lair('SM_ObsidianSpires_B', -44, 2, rng.uniform(0, 360), 360, 330, 'SpiresC', sink=40)
for k in range(5):
    lair('SM_EmberCrystals', rng.uniform(-30, 20), rng.uniform(-28, 28), rng.uniform(0, 360), 150, 140, 'Crystals%d' % k)
for k in range(7):
    lair('SM_LavaRock_%s' % 'ABC'[k % 3], rng.uniform(8, 40), rng.uniform(-40, 40), rng.uniform(0, 360), 160, 120, 'LavaRock%d' % k)
report.append('lair at (%.0f, %.0f) m on the caldera floor (nest burial %.0f cm), %.0f m from the lake centre' % (
    lr['x'], lr['y'], b_n, lr['lair_radius_m']))

# Lava lake: a smaller central lake whose edge follows the floor's bumps (glow only below LavaTop, 10 m above the
# mean floor), instead of a hard bright disc over the whole floor. Same values as tools/build_archipelago.py.
mel = unreal.MaterialEditingLibrary
mi = eal.load_asset('/Game/DragonRider/Archipelago/MI_Land_Ember')
cal = ARCH.layout['islands']['ember']['pois']['caldera']
if mi:
    for k, v in (('LavaRadiusCm', SITES['lair']['lake_radius_m'] * 100.0), ('LavaTopCm', cal['z'] * 100.0 + 1000.0), ('LavaGlow', 2.5)):
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    mel.set_material_instance_vector_parameter_value(mi, 'LavaColor', unreal.LinearColor(1.0, 0.16, 0.02, 1.0))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi)
    report.append('lava lake: radius %.0f m, glow below %.0f m' % (SITES['lair']['lake_radius_m'], cal['z'] + 10.0))

# ---------------------------------------------------------------- coasts: wrecks, driftwood, beacons
counts = {}
for k, p in enumerate(SITES['coast']):
    x, y, sea = p['x'] * 100.0, p['y'] * 100.0, p['sea_deg']
    tag = '%s_%s%d' % (p['island'], p['kind'], k)
    if p['kind'] == 'wreck':
        grounded('SM_WreckBow', x, y, sea + rng.uniform(-30, 30), 470, 240, 'Coast', 'Coast_' + tag + '_Bow', sink=10)
        ox = x + 900 * math.cos(math.radians(sea + 100)); oy = y + 900 * math.sin(math.radians(sea + 100))
        grounded('SM_WreckStern', ox, oy, sea + 180 + rng.uniform(-40, 40), 470, 240, 'Coast', 'Coast_' + tag + '_Stern', sink=10)
    elif p['kind'] == 'driftwood':
        grounded('SM_DriftwoodPile', x, y, rng.uniform(0, 360), 290, 280, 'Coast', 'Coast_' + tag, collide=False)
    else:
        grounded('SM_BeaconTower', x, y, rng.uniform(0, 360), 300, 270, 'Coast', 'Coast_' + tag, sink=30)
    counts[p['kind']] = counts.get(p['kind'], 0) + 1
report.append('coast: %s' % counts)


# ---------------------------------------------------------------- review legs (tools/Review-Archipelago.ps1)
legs_n = 0
for act in actors.get_all_level_actors():
    for t in act.get_editor_property('tags'):
        if str(t).startswith('ReviewLeg:'):
            legs_n = max(legs_n, int(str(t).split(':')[1]) + 1)


def safe_alt(x, y, z):
    """Legs teleport without a sweep: keep the start point at least 60 m above the ground under it."""
    return max(z, height(x, y) + 6000.0)


def leg(name, x, y, z, aim, dur=5.0, shots=(3.5,), speed=90):
    global legs_n
    z = safe_alt(x, y, z)
    pitch = max(-40.0, min(10.0, math.degrees(math.atan2(aim[2] - z, math.hypot(aim[0] - x, aim[1] - y)))))
    m = actors.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(x, y, z), unreal.Rotator(0, 0, 0))
    m.set_actor_label('Review_%02d_%s' % (legs_n, name.replace(' ', '_')))
    m.set_folder_path(FOLDER + '/Review')
    m.set_editor_property('is_spatially_loaded', False)
    m.set_editor_property('tags', [unreal.Name(t) for t in (
        'DR_Landmark', 'ReviewLeg:%02d' % legs_n, 'Name:' + name.replace(' ', '_'), 'Dur:%.1f' % dur,
        'Shots:' + '|'.join('%.1f' % s for s in shots), 'Pitch:%.1f' % pitch, 'Speed:%d' % speed,
        'AimAt:%.0f,%.0f,%.0f' % aim)])
    placed.append(m)
    legs_n += 1


def toward(x, y, deg, dist):
    return x + dist * math.cos(math.radians(deg)), y + dist * math.sin(math.radians(deg))

hz = height(cx, cy)
ex, ey = toward(cx, cy, g, 42000)
leg('stronghold', ex, ey, hz + 16000, (cx, cy, hz + 800))
ex, ey = toward(cx, cy, g + 140, 30000)
leg('stronghold hall', ex, ey, hz + 9000, (cx, cy, hz + 600), speed=70)
wx, wy = along(t_sheet + 26000)
mx, my = along((t_lip + t_base) / 2)
leg('waterfall', wx + uy * 9000, wy - ux * 9000, drop * 0.85, (mx, my, drop * 0.55), speed=40)   # level with the crest: the whole fall in view
cz = height(rx, ry)
ex, ey = toward(rx, ry, path_yaw + 180, 9000)
leg('rune circle', ex, ey, cz + 3500, (rx, ry, cz + 300), speed=30)
sz = height(sx, sy)
ex, ey = toward(sx, sy, path_yaw + 200, 7000)
leg('ice shrine', ex, ey, sz + 2500, (sx, sy, sz + 600), speed=30)
cxl, cyl = SITES['lair']['centre_x'] * 100.0, SITES['lair']['centre_y'] * 100.0
fz = height(px, py)
ex, ey = toward(px, py, face + 180, 9000)
leg('dragon lair', ex, ey, fz + 6500, (px + fx * 4000, py + fy * 4000, fz), speed=30)
seen = set()
for p in SITES['coast']:
    if (p['island'], p['kind']) in seen:
        continue
    seen.add((p['island'], p['kind']))
    if (p['island'], p['kind']) in (('main', 'wreck'), ('main', 'beacon'), ('ember', 'wreck'), ('forest', 'beacon')):
        x, y = p['x'] * 100.0, p['y'] * 100.0
        far = 9000 if p['kind'] == 'wreck' else 16000
        ex, ey = toward(x, y, p['sea_deg'], far)
        leg('%s %s' % (p['island'], p['kind']), ex, ey, height(x, y) + (2200 if p['kind'] == 'wreck' else 3500),
            (x, y, height(x, y) + 300), speed=30)
for act in actors.get_all_level_actors():
    if 'Name:plunge' in [str(t) for t in act.get_editor_property('tags')] and abs(act.get_actor_location().x - 760000.0) > 1.0:
        act.set_actor_location(unreal.Vector(760000.0, 770000.0, 38000.0), False, True)   # same spot build_archipelago.py now uses
        placed.append(act)
        report.append('moved the plunge review leg to deep open sea (7.6, 7.7 km)')
log('review legs now end at %d' % legs_n)

for line in report:
    log(line)
# Save only this script's actor packages (World Partition keeps one package per actor) and the packages of the
# actors it removed, so nothing else (above all the landscape proxies) is rewritten.
pkgs = [a.get_package() for a in placed] + removed
# + the new actor-folder objects (World Partition stores folders as small external objects)
pkgs += [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() if '__ExternalObjects__' in p.get_path_name()]
ours = {p.get_path_name() for p in pkgs}
dirty_other = [p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() +
               unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages() if p.get_path_name() not in ours]
log('left unsaved (not ours): %d dirty packages %s' % (len(dirty_other), dirty_other[:5]))
if not unreal.EditorLoadingAndSavingUtils.save_packages(pkgs, False):
    raise RuntimeError('Saving landmark actors failed')
log('%d landmark actors saved (%d removed)' % (len(placed), len(removed)))
unreal.log('PLACE_LANDMARKS_DONE')
