"""Place the Viking villages and the longship fleet in the archipelago level.

Run headless after tools/import_world_kit.py (tools/build_archipelago.py also runs this at its end):
  UnrealEditor-Cmd.exe <DragonRider.uproject> -run=pythonscript -script="<this file>"
Rerunnable: deletes and recreates only actors in the Archipelago/Villages and Archipelago/Fleet folders.

The village builder (spawning helpers, build_village) is the same as tools/place_world.py's, copied so the old
opening level's script stays untouched. Grounding samples the islands' heightmaps (Saved/Generated/Archipelago/*.r16,
the same data the landscapes were imported from), because line traces return nothing in a commandlet.
Village sites come from archipelago.json (flat ground beside deep water, picked by tools/terrain/gen_archipelago.py).
Fleet: ships row between islands along archipelago.json's fleet_routes and loop back to the start of their route
(ALongshipActor's land-ahead check) when they reach the far shore.
"""
import array
import json
import math
import os
import random
import unreal

LEVEL = '/Game/DragonRider/Archipelago/Lvl_Archipelago'
KIT = '/Game/DragonRider/World/Meshes/'
FOLDERS = ('Archipelago/Villages', 'Archipelago/Fleet')
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
GEN = os.path.join(PROJECT_DIR, 'Saved', 'Generated', 'Archipelago')
LAYOUT = json.load(open(os.path.join(GEN, 'archipelago.json')))

eal = unreal.EditorAssetLibrary
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LongshipClass = unreal.load_class(None, '/Script/DragonRider.LongshipActor')
rng = random.Random(1066)


def log(msg):
    unreal.log('PLACE_ARCHIPELAGO: ' + msg)


world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not world or world.get_path_name().split('.')[0] != LEVEL:
    levels.load_level(LEVEL)
removed_pkgs = []
for a in actors.get_all_level_actors():
    if str(a.get_folder_path()) in FOLDERS:
        removed_pkgs.append(a.get_package())
        actors.destroy_actor(a)


# ---------------------------------------------------------------- heightmap sampler (cm, world space)
class Heightmap:
    def __init__(self, isl):
        self.n = isl['size_px']
        self.step = isl['m_per_px'] * 100.0
        self.x0, self.y0 = isl['landscape_location_cm'][0], isl['landscape_location_cm'][1]
        self.x1, self.y1 = self.x0 + self.step * (self.n - 1), self.y0 + self.step * (self.n - 1)
        self.zs = isl['z_scale'] / 128.0
        self.v = array.array('H')
        with open(os.path.join(GEN, isl['heightmap']), 'rb') as f:
            self.v.fromfile(f, self.n * self.n)

    def get(self, x, y):
        if x < self.x0 or y < self.y0 or x >= self.x1 or y >= self.y1:
            return None
        fx, fy = (x - self.x0) / self.step, (y - self.y0) / self.step
        i, j = int(fx), int(fy)
        u, w = fx - i, fy - j
        k = j * self.n + i
        V, n = self.v, self.n
        h = (V[k] * (1 - u) + V[k + 1] * u) * (1 - w) + (V[k + n] * (1 - u) + V[k + n + 1] * u) * w
        return (h - 32768.0) * self.zs


MAPS = [Heightmap(isl) for isl in LAYOUT['islands'].values()]
OPEN_SEA = -6000.0


def height(x, y):
    best = None
    for m in MAPS:
        h = m.get(x, y)
        if h is not None and (best is None or h > best):
            best = h
    return OPEN_SEA if best is None else best


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


def place(name, x, y, z, yaw, label, folder='Archipelago/Villages', scale=1.0, collide=True):
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
    lh = site('SM_Longhouse', 0, 4500, door_yaw, 60) or site('SM_Longhouse', 0, 2600, door_yaw, 260)
    if not lh:
        log('%s: no longhouse site' % name)
        return None
    a = place('SM_Longhouse', lh[0], lh[1], lh[2], lh[3], name + '_Longhouse')
    a.set_editor_property('tags', [unreal.Name(tag), unreal.Name('DragonVillage')])
    for i in range(n_huts):
        kind = ['SM_Hut', 'SM_Hut', 'SM_Storehouse', 'SM_Smithy', 'SM_Hut'][i % 5]
        s = (site(kind, 1500, 5000, sea_deg - 90 + rng.uniform(-40, 40), 45) or
             site(kind, 1500, 4300, sea_deg - 90 + rng.uniform(-40, 40), 170) or site(kind, 1500, 6000, sea_deg - 90, 220))
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
        log('%s pier %d at (%.0f, %.0f) m over ground %.2f m' % (name, k, px / 100, py / 100, height(px, py) / 100))
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
        ship(mx, my, sea_deg + rng.uniform(-4, 4), clan == 'B', 0.0, '%s_Ship%d' % (name, k), 'Archipelago/Villages')
        log('%s moored ship %d at (%.0f, %.0f) m, ground %.1f m; pier end (%.0f, %.0f) m' % (name, k, mx / 100, my / 100, height(mx, my) / 100, end_x / 100, end_y / 100))

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



def always_loaded():
    for a in actors.get_all_level_actors():
        if str(a.get_folder_path()) in FOLDERS:
            a.set_editor_property('is_spatially_loaded', False)


# ---------------------------------------------------------------- villages (sites from archipelago.json)
I = LAYOUT['islands']
VILLAGES = []
if 'village' in I.get('main', {}).get('pois', {}):
    VILLAGES.append((I['main']['pois']['village'], 'A', 5, 2))
if 'village' in I.get('forest', {}).get('pois', {}):
    v = dict(I['forest']['pois']['village'])
    lm = os.path.join(GEN, 'landmarks.json')
    if os.path.exists(lm):
        site = json.load(open(lm)).get('forest_village')   # flatter site picked by pick_landmark_sites.py
        if site:
            v.update(x=site['x'], y=site['y'])
    VILLAGES.append((v, 'B', 4, 1))
for v, clan, huts, ships in VILLAGES:
    if not build_village(v['name'], v['x'] * 100.0, v['y'] * 100.0, clan, huts, ships):
        log('village %s could not be placed' % v['name'])


# ---------------------------------------------------------------- fleet: ships rowing between the islands
def route_sea_span(a, b):
    """Longest open-water stretch of the straight line from island a's centre to island b's (cm), with deep water
    (15 m+) under the line and on both sides: (start, dir, length)."""
    ax, ay = a[0] * 100.0, a[1] * 100.0
    bx, by = b[0] * 100.0, b[1] * 100.0
    L = math.hypot(bx - ax, by - ay)
    dx, dy = (bx - ax) / L, (by - ay) / L
    best, run0 = None, None
    for k in range(0, int(L) + 2000, 2000):
        deep = k <= L and height(ax + dx * k, ay + dy * k) < -1500 and max(
            height(ax + dx * k - dy * o, ay + dy * k + dx * o) for o in (-2500, 2500)) < -1200
        if deep and run0 is None:
            run0 = k
        if not deep and run0 is not None:
            if best is None or k - run0 > best[1] - best[0]:
                best = (run0, k - 2000)
            run0 = None
    if best is None:
        return None
    return (ax + dx * best[0], ay + dy * best[0]), (dx, dy), best[1] - best[0]


fleet = 0
for r in LAYOUT.get('fleet_routes', []):
    if r['src'] not in I or r['dst'] not in I:
        continue
    span = route_sea_span(I[r['src']]['centre'], I[r['dst']]['centre'])
    if not span:
        log('route %s -> %s has no open water' % (r['src'], r['dst']))
        continue
    (sx, sy), (dx, dy), length = span
    yaw = math.degrees(math.atan2(dy, dx))
    for k in range(r['ships']):
        t = (0.05 + 0.25 * k / max(1, r['ships'])) * length   # near the start: each crossing lasts the whole route
        off = rng.uniform(-1500, 1500)
        x, y = sx + dx * t - dy * off, sy + dy * t + dx * off
        a = ship(x, y, yaw + rng.uniform(-2, 2), (fleet % 2) == 1, rng.uniform(480, 560),
                 'Fleet_%s_%s_%d' % (r['src'], r['dst'], k), 'Archipelago/Fleet')
        a.set_editor_property('return_to_start', True)   # rows to the far shore, then starts its crossing again
        fleet += 1
    log('route %s -> %s: %d ships over %.1f km of open sea, heading %.0f' % (r['src'], r['dst'], r['ships'], length / 100000.0, yaw))

# Review leg (tools/Review-Archipelago.ps1): low pass along the first route's ships, appended after the others.
first_ship = None
for act in actors.get_all_level_actors():
    if str(act.get_folder_path()) == 'Archipelago/Fleet' and first_ship is None:
        first_ship = act
legs_n = 0
for act in actors.get_all_level_actors():
    for t in act.get_editor_property('tags'):
        if str(t).startswith('ReviewLeg:'):
            legs_n = max(legs_n, int(str(t).split(':')[1]) + 1)
if first_ship:
    p = first_ship.get_actor_location()
    f = first_ship.get_actor_forward_vector()
    r = unreal.Vector(-f.y, f.x, 0.0)
    # The leg starts ~105 s into the review; by then the ship has rowed ~5.2 m/s * 105 s further along its route.
    ahead = first_ship.get_editor_property('sail_speed') * 105.0
    p = unreal.Vector(p.x + f.x * ahead, p.y + f.y * ahead, 0.0)
    loc = unreal.Vector(p.x - f.x * 9000.0 + r.x * 3500.0, p.y - f.y * 9000.0 + r.y * 3500.0, 7000.0)
    m = actors.spawn_actor_from_class(unreal.TargetPoint, loc, unreal.Rotator(0, 0, 0))
    m.set_actor_label('Review_%02d_fleet' % legs_n)
    m.set_folder_path('Archipelago/Fleet')
    m.set_editor_property('tags', [unreal.Name(t) for t in (
        'ReviewLeg:%02d' % legs_n, 'Name:fleet', 'Dur:7.0', 'Shots:4.0|6.0', 'Pitch:-4.0', 'Speed:60',
        'FollowShip:6000,3200,4500')])
    log('fleet review leg %d behind %s' % (legs_n, first_ship.get_actor_label()))

# Review leg: the forest village (Lundvik) seen from the sea in front of its longhouse.
for act in actors.get_all_level_actors():
    if act.get_actor_label() == 'Lundvik_Longhouse':
        p = act.get_actor_location()
        rv = act.get_actor_right_vector()   # doors (+Y) face the water
        loc = unreal.Vector(p.x + rv.x * 16000.0, p.y + rv.y * 16000.0, p.z + 4500.0)
        m = actors.spawn_actor_from_class(unreal.TargetPoint, loc, unreal.Rotator(0, 0, 0))
        m.set_actor_label('Review_%02d_forest_village_close' % (legs_n + 1))
        m.set_folder_path('Archipelago/Villages')
        m.set_editor_property('tags', [unreal.Name(t) for t in (
            'ReviewLeg:%02d' % (legs_n + 1), 'Name:forest_village_close', 'Dur:5.0', 'Shots:3.5', 'Pitch:-14.0', 'Speed:40',
            'AimAt:%.0f,%.0f,%.0f' % (p.x, p.y, p.z + 300.0))])
        break
for act in actors.get_all_level_actors():
    if act.get_actor_label() == 'Lundvik_Pier4':
        p = act.get_actor_location()
        f = act.get_actor_forward_vector()   # pier runs out to sea along +X
        r = unreal.Vector(-f.y, f.x, 0.0)
        loc = unreal.Vector(p.x + f.x * 5000.0 + r.x * 5000.0, p.y + f.y * 5000.0 + r.y * 5000.0, 2500.0)
        m = actors.spawn_actor_from_class(unreal.TargetPoint, loc, unreal.Rotator(0, 0, 0))
        m.set_actor_label('Review_%02d_lundvik_pier' % (legs_n + 2))
        m.set_folder_path('Archipelago/Villages')
        m.set_editor_property('tags', [unreal.Name(t) for t in (
            'ReviewLeg:%02d' % (legs_n + 2), 'Name:lundvik_pier', 'Dur:4.0', 'Shots:2.5', 'Pitch:-18.0', 'Speed:30',
            'AimAt:%.0f,%.0f,%.0f' % (p.x - f.x * 1500.0, p.y - f.y * 1500.0, 100.0))])
        break

always_loaded()
# Save only this script's actor packages (and the ones it removed) plus new actor-folder objects, never the
# landscapes: every landscape rewrite costs ~200 MB of Git LFS.
own = [a.get_package() for a in actors.get_all_level_actors() if str(a.get_folder_path()) in FOLDERS]
own += removed_pkgs
own += [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() if '__ExternalObjects__' in p.get_path_name()]
if not unreal.EditorLoadingAndSavingUtils.save_packages(own, False):
    raise RuntimeError('Saving village/fleet actors failed')
log('%d villages, %d fleet ships' % (len(VILLAGES), fleet))
unreal.log('PLACE_ARCHIPELAGO_DONE')
