"""Build the Viking village + fleet prop kit headlessly.

Run:
  blender.exe -b --factory-startup --python tools/blender/world/build_props.py

Writes to Game/DragonRider/Saved/Generated/World/:
  T_*.png textures, SM_*.fbx (one per prop / animatable part), VikingKit.glb (web),
  VikingKit.blend (source for render_previews.py), props_manifest.json.
"""
import json
import math
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(REPO, "Game", "DragonRider", "Saved", "Generated", "World")
os.makedirs(OUT, exist_ok=True)

import kit_textures  # noqa: E402
import kit_props as P  # noqa: E402
from kit_geo import tri_count  # noqa: E402

T0 = time.time()

# --------------------------------------------------------------------------- scene reset
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
for coll in list(bpy.data.collections):
    bpy.data.collections.remove(coll)
for m in list(bpy.data.meshes):
    bpy.data.meshes.remove(m)
for m in list(bpy.data.materials):
    bpy.data.materials.remove(m)
bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 1.0

# --------------------------------------------------------------------------- textures + materials
TEX = kit_textures.build_all(bpy, OUT)
print(f"textures done {time.time() - T0:.1f}s")


def make_mat(name, bc, nrm, rough, metallic=0.0, double=False, nstrength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bs.outputs[0], out.inputs[0])
    t_bc = nt.nodes.new("ShaderNodeTexImage")
    t_bc.image = bc
    t_bc.location = (-500, 300)
    nt.links.new(t_bc.outputs["Color"], bs.inputs["Base Color"])
    t_r = nt.nodes.new("ShaderNodeTexImage")
    t_r.image = rough
    t_r.location = (-500, 0)
    nt.links.new(t_r.outputs["Color"], bs.inputs["Roughness"])
    t_n = nt.nodes.new("ShaderNodeTexImage")
    t_n.image = nrm
    t_n.location = (-500, -300)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (-200, -300)
    nm.inputs["Strength"].default_value = nstrength
    nt.links.new(t_n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bs.inputs["Normal"])
    bs.inputs["Metallic"].default_value = metallic
    m.use_backface_culling = not double
    m["textures"] = [bc.name + ".png", nrm.name + ".png", rough.name + ".png"]
    return m


MATS = {
    "M_Wood": make_mat("M_Wood", TEX["T_Wood"]["BC"], TEX["T_Wood"]["N"], TEX["T_Wood"]["R"]),
    "M_WoodTar": make_mat("M_WoodTar", TEX["T_WoodTar"]["BC"], TEX["T_WoodTar"]["N"], TEX["T_WoodTar"]["R"]),
    "M_Turf": make_mat("M_Turf", TEX["T_Turf"]["BC"], TEX["T_Turf"]["N"], TEX["T_Turf"]["R"]),
    "M_Iron": make_mat("M_Iron", TEX["T_Iron"]["BC"], TEX["T_Iron"]["N"], TEX["T_Iron"]["R"], metallic=0.6),
    "M_Stone": make_mat("M_Stone", TEX["T_Stone"]["BC"], TEX["T_Stone"]["N"], TEX["T_Stone"]["R"]),
}
for clan in ("ClanA", "ClanB"):
    MATS[f"M_Shields_{clan}"] = make_mat(f"M_Shields_{clan}", TEX[f"T_Shields_{clan}"]["BC"], TEX["T_Shields"]["N"],
                                         TEX["T_Shields"]["R"])
    MATS[f"M_Sail_{clan}"] = make_mat(f"M_Sail_{clan}", TEX[f"T_Sail_{clan}"]["BC"], TEX["T_Cloth"]["N"],
                                      TEX["T_Cloth"]["R"], double=True)
    MATS[f"M_Banner_{clan}"] = make_mat(f"M_Banner_{clan}", TEX[f"T_Banner_{clan}"]["BC"], TEX["T_Cloth"]["N"],
                                        TEX["T_Cloth"]["R"], double=True)


def matmap(clan):
    d = dict(MATS)
    d["M_Shields"] = MATS[f"M_Shields_{clan}"]
    d["M_Sail"] = MATS[f"M_Sail_{clan}"]
    d["M_Banner"] = MATS[f"M_Banner_{clan}"]
    return d


def new_coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def put(ob, coll):
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll.objects.link(ob)


# --------------------------------------------------------------------------- build
EXPORTS = []      # (fbx file, object) - each exported alone at identity transform
MANIFEST = {"units": "metres in Blender / exported as centimetres for Unreal (1 m = 100 uu)",
            "axes": "Blender +X forward, +Z up; FBX converted for Unreal so +X stays forward",
            "normal_maps": "*_N.png = OpenGL (+Y, used by Blender/glTF). *_N_DX.png = DirectX green for Unreal "
                           "(or use *_N.png with 'Flip Green Channel').",
            "texture_tiling": {"M_Wood": "2 m per UV unit", "M_WoodTar": "2 m", "M_Turf": "4 m", "M_Iron": "1 m",
                               "M_Stone": "2 m", "M_Shields_*": "4x4 atlas, unique UVs", "M_Sail_*": "0..1 over the sail",
                               "M_Banner_*": "0..1 over the cloth"},
            "two_sided_materials": ["M_Sail_ClanA", "M_Sail_ClanB", "M_Banner_ClanA", "M_Banner_ClanB"],
            "glb": "VikingKit.glb", "props": []}
STATS = {}

t = time.time()
mb_ship = P.build_longship()
mb_sail = P.build_sail()
mb_oar = P.build_oar()
oar_mesh = mb_oar.build(MATS, name="SM_LongshipOar")
oar_mesh_data = oar_mesh.data
bpy.data.objects.remove(oar_mesh)
pivots = P.oar_pivots()
ship_roots = {}
for clan in ("ClanA", "ClanB"):
    coll = new_coll(f"Longship_{clan}")
    hull = mb_ship.build(matmap(clan), name=f"SM_Longship_{clan}")
    put(hull, coll)
    sail = mb_sail.build(matmap(clan), name=f"SM_LongshipSail_{clan}", location=P.YARD)
    put(sail, coll)
    sail.parent = hull
    for k, (p, rot, side) in enumerate(pivots):
        o = bpy.data.objects.new(f"Oar_{clan}_{side}_{k % 16:02d}", oar_mesh_data)
        o.location = p
        o.rotation_euler = rot
        coll.objects.link(o)
        o.parent = hull
    ship_roots[clan] = hull
    EXPORTS.append((f"SM_Longship_{clan}.fbx", hull))
    EXPORTS.append((f"SM_LongshipSail_{clan}.fbx", sail))
oar_holder = bpy.data.objects.new("SM_LongshipOar", oar_mesh_data)
bpy.data.collections["Longship_ClanA"].objects.link(oar_holder)
oar_holder.hide_render = True
oar_holder.hide_viewport = True
EXPORTS.append(("SM_LongshipOar.fbx", oar_holder))
print(f"longship built {time.time() - t:.1f}s")

hullA = ship_roots["ClanA"]
tri_hull = tri_count(hullA)
tri_sail = tri_count(bpy.data.objects["SM_LongshipSail_ClanA"])
tri_oar = len(oar_mesh_data.polygons)
ship_total = tri_hull + tri_sail + 32 * tri_oar


def bbox(objs):
    bpy.context.view_layer.update()
    import mathutils
    lo = mathutils.Vector((1e9, 1e9, 1e9))
    hi = -lo
    for ob in objs:
        if ob.type != "MESH" or ob.hide_render:
            continue
        mw = ob.matrix_world
        for v in ob.data.vertices:
            w = mw @ v.co
            lo = mathutils.Vector(map(min, lo, w))
            hi = mathutils.Vector(map(max, hi, w))
    return [round(c, 3) for c in lo], [round(c, 3) for c in hi]


def mats_of(ob):
    out = {}
    for m in ob.data.materials:
        out[m.name] = list(m["textures"])
    return out


lo, hi = bbox([hullA] + list(hullA.children))
MANIFEST["props"].append({
    "name": "Longship",
    "variants": ["ClanA (red/white)", "ClanB (blue/ochre)"],
    "fbx": {"hull_ClanA": "SM_Longship_ClanA.fbx", "hull_ClanB": "SM_Longship_ClanB.fbx",
            "sail_ClanA": "SM_LongshipSail_ClanA.fbx", "sail_ClanB": "SM_LongshipSail_ClanB.fbx",
            "oar": "SM_LongshipOar.fbx"},
    "glb_nodes": ["SM_Longship_ClanA", "SM_Longship_ClanB"],
    "origin": "waterline, hull centre; +X = bow",
    "bbox_min_m": lo, "bbox_max_m": hi, "size_m": [round(h - l, 2) for l, h in zip(lo, hi)],
    "triangles": {"hull": tri_hull, "sail": tri_sail, "oar_each": tri_oar, "oars": 32, "total_assembled": ship_total},
    "materials": {**mats_of(hullA), **mats_of(bpy.data.objects["SM_LongshipSail_ClanA"]), **mats_of(oar_holder)},
    "attach_points": {
        "sail": {"mesh": "SM_LongshipSail_<Clan>", "location_m": [round(c, 3) for c in P.YARD], "rotation_deg": [0, 0, 0],
                 "note": "sail pivot = yard centre (top edge of sail). Sail mesh hangs down -Z and bellies +X; "
                         "u across the sail, v bottom->top for cloth sim pinning (pin top row v=1)."},
        "mast_top_m": [P.MAST_X, 0, 11.7],
        "oars": [{"name": f"{side}_{k % 16:02d}", "side": side, "location_m": [round(c, 3) for c in p],
                  "rotation_deg_xyz": [round(math.degrees(r), 2) for r in rot]}
                 for k, (p, rot, side) in enumerate(pivots)],
        "oar_note": "SM_LongshipOar pivot = oar port. Blade points along local +Y, handle -Y. Rowing = rotate "
                    "about local Z (sweep, +-25 deg) and local X (lift, -12 deg rest, -2 deg recovery). Port side "
                    "+Y, starboard -Y (yaw 180).",
    },
})

# ---------------------------------------------------------------- static props
STATIC = [
    ("Longhouse", P.build_longhouse, "25 x 7 m turf-roofed longhouse; doors on +Y side and -X gable; smoke louvre on ridge"),
    ("Hut", P.build_hut, "turf cottage 7 x 4.6 m; vary by scale (0.8-1.15) and rotation"),
    ("Storehouse", P.build_storehouse, "raised storehouse on stilts 3.6 x 3 m"),
    ("Smithy", P.build_smithy, "open-fronted smithy (+Y open) with forge, anvil, quench tub"),
    ("PierSection", lambda: P.build_pier(False), "pier module, 5 m along X, deck at +1.0 m; tile at 5 m"),
    ("PierEnd", lambda: P.build_pier(True), "pier end module (+X end) with mooring posts + ladder; tile after sections"),
    ("PalisadeWall", P.build_palisade, "palisade segment 6 m along X, inside = -Y; tile at 6 m"),
    ("PalisadeGate", P.build_gate, "palisade gate segment 6 m, 3 m opening, right leaf ajar"),
    ("Watchtower", P.build_watchtower, "watchtower 3 m footprint, platform at 7 m, roof apex 11 m"),
    ("Barrel", P.build_barrel, "barrel 0.9 m"),
    ("Crate", P.build_crate, "crate 0.95 x 0.7 x 0.6 m"),
    ("WoodPile", P.build_woodpile, "split-log woodpile 2.2 m"),
]
for name, fn, note in STATIC:
    t = time.time()
    mb = fn()
    coll = new_coll(name)
    ob = mb.build(MATS, name=f"SM_{name}")
    put(ob, coll)
    EXPORTS.append((f"SM_{name}.fbx", ob))
    lo, hi = bbox([ob])
    MANIFEST["props"].append({"name": name, "fbx": f"SM_{name}.fbx", "glb_nodes": [f"SM_{name}"], "note": note,
                              "origin": "base centre (pier: waterline under deck centre)",
                              "bbox_min_m": lo, "bbox_max_m": hi, "size_m": [round(h - l, 2) for l, h in zip(lo, hi)],
                              "triangles": tri_count(ob), "materials": mats_of(ob)})
    print(f"{name}: {tri_count(ob)} tris {time.time() - t:.1f}s")

# banner pole + cloth (two clans)
mb_pole = P.build_banner_pole()
mb_cloth = P.build_banner_cloth()
for clan in ("ClanA", "ClanB"):
    coll = new_coll(f"Banner_{clan}")
    pole = mb_pole.build(MATS, name=f"SM_Banner_{clan}")
    put(pole, coll)
    cloth = mb_cloth.build(matmap(clan), name=f"SM_BannerCloth_{clan}", location=P.BANNER_ATTACH)
    put(cloth, coll)
    cloth.parent = pole
    if clan == "ClanA":
        EXPORTS.append(("SM_BannerPole.fbx", pole))
    EXPORTS.append((f"SM_BannerCloth_{clan}.fbx", cloth))
poleA = bpy.data.objects["SM_Banner_ClanA"]
lo, hi = bbox([poleA, bpy.data.objects["SM_BannerCloth_ClanA"]])
MANIFEST["props"].append({
    "name": "Banner", "fbx": {"pole": "SM_BannerPole.fbx", "cloth_ClanA": "SM_BannerCloth_ClanA.fbx",
                              "cloth_ClanB": "SM_BannerCloth_ClanB.fbx"},
    "glb_nodes": ["SM_Banner_ClanA", "SM_Banner_ClanB"], "origin": "base of pole",
    "bbox_min_m": lo, "bbox_max_m": hi, "size_m": [round(h - l, 2) for l, h in zip(lo, hi)],
    "triangles": {"pole": tri_count(poleA), "cloth": tri_count(bpy.data.objects["SM_BannerCloth_ClanA"])},
    "materials": {**mats_of(poleA), **mats_of(bpy.data.objects["SM_BannerCloth_ClanA"]),
                  **mats_of(bpy.data.objects["SM_BannerCloth_ClanB"])},
    "attach_points": {"cloth": {"location_m": [round(c, 3) for c in P.BANNER_ATTACH], "rotation_deg": [0, 0, 0],
                                "note": "cloth pivot = crossbar centre; pin top row (v=1) for cloth sim"}},
})

# --------------------------------------------------------------------------- save .blend
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "VikingKit.blend"), relative_remap=True)

# --------------------------------------------------------------------------- FBX exports
FBX_SETTINGS = dict(use_selection=True, object_types={"MESH"}, apply_unit_scale=True,
                    apply_scale_options="FBX_SCALE_ALL", global_scale=1.0, axis_forward="-Z", axis_up="Y",
                    use_space_transform=True, bake_space_transform=False, mesh_smooth_type="FACE",
                    use_mesh_modifiers=True, use_tspace=True, add_leaf_bones=False, bake_anim=False,
                    path_mode="RELATIVE", embed_textures=False)
for fname, ob in EXPORTS:
    base = os.path.splitext(fname)[0]
    orig = ob.name
    ob.name = orig + "__src"
    tmp = bpy.data.objects.new(base, ob.data)
    bpy.context.scene.collection.objects.link(tmp)
    bpy.ops.object.select_all(action="DESELECT")
    tmp.select_set(True)
    bpy.context.view_layer.objects.active = tmp
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, fname), **FBX_SETTINGS)
    bpy.data.objects.remove(tmp)
    ob.name = orig
print(f"fbx done {time.time() - T0:.1f}s")

# --------------------------------------------------------------------------- GLB (web): 1024 px JPEG textures
for img in bpy.data.images:
    if img.size[0] > 1024:
        img.scale(1024, 1024)
bpy.ops.object.select_all(action="DESELECT")
for ob in bpy.data.objects:
    if ob.name == "SM_LongshipOar":
        continue
    ob.select_set(True)
glb = os.path.join(OUT, "VikingKit.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_image_format="JPEG",
                          export_jpeg_quality=85, export_yup=True, export_apply=False, export_materials="EXPORT")
MANIFEST["glb_size_mb"] = round(os.path.getsize(glb) / 1e6, 2)
MANIFEST["glb_note"] = ("All prop roots sit at the origin (named nodes) - instance them by name. Textures in the glb are "
                        "1024 px JPEG copies of the PNGs.")
MANIFEST["fbx_export_settings"] = {k: (sorted(v) if isinstance(v, set) else v) for k, v in FBX_SETTINGS.items()}
MANIFEST["outside_assets"] = "none - all geometry and textures generated procedurally by tools/blender/world/*.py"
with open(os.path.join(OUT, "props_manifest.json"), "w") as f:
    json.dump(MANIFEST, f, indent=1)
print("TRIS longship hull", tri_hull, "sail", tri_sail, "oar", tri_oar, "assembled", ship_total)
print(f"ALL DONE {time.time() - T0:.1f}s glb {MANIFEST['glb_size_mb']} MB")
