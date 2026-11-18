"""Place the Viking villages and the approaching longship fleet in the opening level.

Run headless after tools/import_world_kit.py (build_opening_level.py also runs this at its end):
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Rerunnable: it deletes and recreates only actors in the Opening/Villages and Opening/Fleet folders.

Grounding: line traces return nothing inside the commandlet (no physics scene), so the script samples the
real terrain mesh instead: the fjord terrain is a regular vertex grid, read from its mesh description and
interpolated. Each building is placed at the flattest footprint near its village, set to the lowest
footprint sample (so it never floats) and the uphill burial is reported in the log.
"""
import math
import random
import unreal

LEVEL = '/Game/DragonRider/Opening/Lvl_Opening'
KIT = '/Game/DragonRider/World/Meshes/'
FOLDERS = ('Opening/Villages', 'Opening/Fleet')

eal = unreal.EditorAssetLibrary
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LongshipClass = unreal.load_class(None, '/Script/DragonRider.LongshipActor')
rng = random.Random(1066)


def log(msg):
    unreal.log('PLACE_WORLD: ' + msg)


world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not world or world.get_path_name().split('.')[0] != LEVEL:
    levels.load_level(LEVEL)
for a in actors.get_all_level_actors():
    if str(a.get_folder_path()) in FOLDERS:
        actors.destroy_actor(a)

# ---------------------------------------------------------------- terrain height sampler (cm)
terrain_actor = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'FjordTerrain'][0]
md = terrain_actor.static_mesh_component.static_mesh.get_static_mesh_description(0)
nv = md.get_vertex_count()
xs, ys = set(), set()
pts = []
for i in range(nv):
    p = md.get_vertex_position(unreal.VertexID(i))
    pts.append((p.x, p.y, p.z))
x0 = min(p[0] for p in pts); x1 = max(p[0] for p in pts)
y0 = min(p[1] for p in pts); y1 = max(p[1] for p in pts)
GN = int(round(math.sqrt(nv)))
STEP = (x1 - x0) / (GN - 1)
H = [0.0] * (GN * GN)
for x, y, z in pts:
    H[int(round((y - y0) / STEP)) * GN + int(round((x - x0) / STEP))] = z
del pts
log('terrain grid %dx%d step %.1f cm' % (GN, GN, STEP))


def height(x, y):
    fx = min(max((x - x0) / STEP, 0.0), GN - 1.001)
    fy = min(max((y - y0) / STEP, 0.0), GN - 1.001)
    i, j = int(fx), int(fy)
    u, v = fx - i, fy - j
    k = j * GN + i
    # Match a split-quad triangulation on the safe side: take bilinear, never above the higher triangle.
    return (H[k] * (1 - u) + H[k + 1] * u) * (1 - v) + (H[k + GN] * (1 - u) + H[k + GN + 1] * u) * v


def footprint(x, y, yaw, hx, hy, n=3):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    out = []
    for a in range(n):
        for b in range(n):
            lx = -hx + 2 * hx * a / (n - 1)
            ly = -hy + 2 * hy * b / (n - 1)
            out.append(height(x + lx * c - ly * s, y + lx * s + ly * c))
    return out


# ---------------------------------------------------------------- spawning helpers
meshes = {}
def mesh(name):
    if name not in meshes:
        meshes[name] = eal.load_asset(KIT + name)
        if not meshes[name]:
            raise RuntimeError('Missing world kit mesh %s - run tools/import_world_kit.py first' % name)
    return meshes[name]


def place(name, x, y, z, yaw, label, folder='Opening/Villages', scale=1.0, collide=True):
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.static_mesh_component.set_static_mesh(mesh(name))
    a.set_actor_label(label)
    a.set_folder_path(folder)
    if scale != 1.0:
        a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    if not collide:
        a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    return a


def ship(x, y, yaw, clan_b, speed, label, folder):
    a = actors.spawn_actor_from_class(LongshipClass, unreal.Vector(x, y, 0), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_editor_property('clan_b', clan_b)
    a.set_editor_property('sail_speed', speed)
    a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


# Footprint half-extents (cm) from props_manifest.json bounds (plus a little apron).
BUILD = {
    'SM_Longhouse': (1330, 470), 'SM_Hut': (420, 320), 'SM_Storehouse': (250, 240),
    'SM_Smithy': (340, 300), 'SM_Watchtower': (250, 210),
}


# ---------------------------------------------------------------- villages
def seaward(cx, cy):
    best = None
    for k in range(72):
        a = math.radians(k * 5)
        d = sum(height(cx + r * math.cos(a), cy + r * math.sin(a)) for r in (6000, 10000, 15000))
        if best is None or d < best[0]:
            best = (d, a)
    return best[1]


def build_village(name, cx, cy, clan, n_huts, n_ships):
    tag = 'Village_' + name
    w = seaward(cx, cy)
    wx, wy = math.cos(w), math.sin(w)
    sea_deg = math.degrees(w)
    placed = []  # (x, y, radius)
    report = []

    def free(x, y, r):
        return all(math.hypot(x - px, y - py) > r + pr + 250 for px, py, pr in placed)

    def site(mname, rmin, rmax, yaw_base, max_range, prefer_land=True):
        hx, hy = BUILD[mname]
        rad = math.hypot(hx, hy)
        best = None
        for k in range(600):
            r = rmin + (rmax - rmin) * rng.random()
            a = w + math.pi + (rng.random() - 0.5) * math.radians(250 if prefer_land else 360)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            if not free(x, y, rad):
                continue
            for dyaw in (0, 15, -15, 30, -30):
                yaw = yaw_base + dyaw
                fp = footprint(x, y, yaw, hx, hy)
                lo, hi = min(fp), max(fp)
                if lo < 120 or hi > 4500 or hi - lo > max_range:
                    continue
                score = (hi - lo) + 0.004 * r
                if best is None or score < best[0]:
                    best = (score, x, y, yaw, lo, hi)
        if not best:
            return None
        _, x, y, yaw, lo, hi = best
        placed.append((x, y, rad))
        report.append('%s burial %.0fcm' % (mname[3:], hi - lo))
        return x, y, lo - 15, yaw

    # Longhouse first, doors (+Y) toward the water.
    door_yaw = sea_deg - 90
    lh = site('SM_Longhouse', 0, 2600, door_yaw, 260)
    if not lh:
        log('%s: no longhouse site' % name)
        return None
    a = place('SM_Longhouse', lh[0], lh[1], lh[2], lh[3], name + '_Longhouse')
    a.set_editor_property('tags', [unreal.Name(tag), unreal.Name('DragonVillage')])
    for i in range(n_huts):
        kind = ['SM_Hut', 'SM_Hut', 'SM_Storehouse', 'SM_Smithy', 'SM_Hut'][i % 5]
        s = site(kind, 1500, 4300, sea_deg - 90 + rng.uniform(-40, 40), 170) or site(kind, 1500, 6000, sea_deg - 90, 220)
        if s:
            sc = rng.uniform(0.9, 1.1) if kind == 'SM_Hut' else 1.0
            place(kind, s[0], s[1], s[2], s[3], '%s_%s%d' % (name, kind[3:], i), scale=sc)
            # A couple of props beside each building.
            for p in range(2):
                pk = rng.choice(['SM_Barrel', 'SM_Barrel', 'SM_Crate', 'SM_WoodPile'])
                ang = math.radians(s[3] + rng.choice([0, 180]) + rng.uniform(-25, 25))
                d = BUILD[kind][0] + 160
                px, py = s[0] + d * math.cos(ang), s[1] + d * math.sin(ang)
                fp = footprint(px, py, 0, 60, 60, 2)
                if min(fp) > 80 and max(fp) - min(fp) < 60:
                    place(pk, px, py, min(fp) - 3, rng.uniform(0, 360), '%s_%s%d_%d' % (name, pk[3:], i, p), collide=False)
    # Banner in front of the longhouse doors.
    bx, by = lh[0] + 1100 * math.cos(math.radians(lh[3] + 90)), lh[1] + 1100 * math.sin(math.radians(lh[3] + 90))
    bz = min(footprint(bx, by, 0, 40, 40, 2)) - 20
    place('SM_BannerPole', bx, by, bz, sea_deg, name + '_BannerPole', collide=False)
    place('SM_BannerCloth_Clan' + clan, bx + 4 * math.cos(w), by + 4 * math.sin(w), bz + 482, sea_deg, name + '_Banner', collide=False)

    # Pier: from where the shore drops below +0.5 m, straight out to sea.
    sx, sy = cx, cy
    for k in range(400):
        if height(sx, sy) < 50:
            break
        sx += wx * 100; sy += wy * 100
    sections = 4
    for k in range(sections + 1):
        px, py = sx + wx * (250 + 500 * k), sy + wy * (250 + 500 * k)
        place('SM_PierEnd' if k == sections else 'SM_PierSection', px, py, 0, sea_deg, '%s_Pier%d' % (name, k))
    end_x, end_y = sx + wx * (250 + 500 * sections), sy + wy * (250 + 500 * sections)
    # Moored ships alongside the pier, bows out to sea; pushed out until the hull has water under it.
    for k in range(n_ships):
        side = 1 if k == 0 else -1
        nx, ny = -wy * side, wx * side
        for push in range(0, 6000, 200):
            mx = end_x + nx * 520 + wx * (push - 400)
            my = end_y + ny * 520 + wy * (push - 400)
            if max(footprint(mx, my, sea_deg, 1150, 330)) < -160:
                break
        ship(mx, my, sea_deg + rng.uniform(-4, 4), clan == 'B', 0.0, '%s_Ship%d' % (name, k), 'Opening/Villages')

    # Palisade arc around the landward side, gate facing inland; watchtower at the seaward end of the arc.
    R = max(math.hypot(px - cx, py - cy) + pr for px, py, pr in placed) + 900
    land = w + math.pi
    n_seg = int(R * math.radians(230) / 600)
    gate_i = n_seg // 2
    walls = 0
    for k in range(n_seg + 1):
        a = land - math.radians(115) + (k / n_seg) * math.radians(230)
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        yaw = math.degrees(a) - 90  # local -Y (inside) faces the village centre
        fp = footprint(x, y, yaw, 300, 60, 3)
        if min(fp) < 60 or max(fp) - min(fp) > 320:
            continue
        place('SM_PalisadeGate' if k == gate_i else 'SM_PalisadeWall', x, y, min(fp) - 25, yaw, '%s_Palisade%02d' % (name, k))
        walls += 1
    for end in (-1, 1):
        a = land + end * math.radians(122)
        tx, ty = cx + (R - 500) * math.cos(a), cy + (R - 500) * math.sin(a)
        fp = footprint(tx, ty, 0, 230, 230)
        if min(fp) > 60 and max(fp) - min(fp) < 260:
            place('SM_Watchtower', tx, ty, min(fp) - 30, math.degrees(a), name + '_Watchtower')
            break
    log('%s clan %s at (%.0f, %.0f) m, sea %.0f deg, palisade R=%.0f m (%d segments), %s' % (
        name, clan, cx / 100, cy / 100, sea_deg % 360, R / 100, walls, ', '.join(report)))
    return lh


# Spots chosen from the terrain grid: low slope, 2-40 m above the sea, beside deep water.
# (The fjord in the mesh runs along Y = -centre(x) of build_opening_level.py's formula.)
VILLAGES = [
    ('Skerholm', -615600, -140600, 'A', 4, 2),   # coast just ahead-right of the dragon start
    ('Fjordmunn', -532800, 164100, 'B', 4, 1),   # north shore of the fjord mouth
    ('Innvik', 98400, -7800, 'A', 5, 1),         # flat strip deep inside the fjord
]
for v in VILLAGES:
    build_village(*v)

# ---------------------------------------------------------------- fleet: rowing in from the west sea toward the fjord mouth
FLEET_X, FLEET_Y = -880000, -30000
formation = [(0, 0), (-6500, -5500), (-6500, 5800), (-13500, -10500), (-13000, 11000), (-21000, 0)]
clear = True
for fx, fy in formation:
    for x in range(-1200000, -560000, 4000):
        if height(x, FLEET_Y + fy) > -900 and x - (FLEET_X + fx) < 0 and x > -800000:
            clear = False
for k, (fx, fy) in enumerate(formation):
    ship(FLEET_X + fx + rng.uniform(-800, 800), FLEET_Y + fy + rng.uniform(-600, 600), rng.uniform(-2, 2), k % 2 == 1,
         rng.uniform(480, 560), 'Fleet_Ship%d' % k, 'Opening/Fleet')
log('fleet of %d at (%.0f, %.0f) m heading east; route clear behind start=%s' % (len(formation), FLEET_X / 100, FLEET_Y / 100, clear))

if not levels.save_current_level():
    raise RuntimeError('Level save failed')
unreal.log('PLACE_WORLD_DONE')
