"""Build the archipelago landmark set headlessly (run build_props.py first: it reuses kit textures).

  blender.exe -b --factory-startup --python tools/blender/world/build_landmarks.py

Writes to Game/DragonRider/Saved/Generated/World/: new T_*.png textures, SM_*.fbx per landmark,
Landmarks.glb (web), Landmarks.blend (for render_landmarks.py) and the "landmarks" section of
props_manifest.json.
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

import landmark_textures  # noqa: E402
import landmark_props as LP  # noqa: E402
from kit_geo import tri_count  # noqa: E402

T0 = time.time()
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)
for m in list(bpy.data.meshes):
    bpy.data.meshes.remove(m)
for m in list(bpy.data.materials):
    bpy.data.materials.remove(m)

TEX = {} if os.environ.get("SKIP_TEX") else landmark_textures.build_all(bpy, OUT)
print(f"textures {time.time() - T0:.1f}s")


def load(name, srgb):
    path = os.path.join(OUT, name + ".png")
    img = bpy.data.images.get(name) or bpy.data.images.load(path)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    return img


def make_mat(name, t_bc, t_n, t_r, t_e=None, e_strength=0.0, metallic=0.0, alpha=False, double=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bs.outputs[0], out.inputs[0])
    bc = nt.nodes.new("ShaderNodeTexImage")
    bc.image = load(t_bc, True)
    nt.links.new(bc.outputs["Color"], bs.inputs["Base Color"])
    if alpha:
        nt.links.new(bc.outputs["Alpha"], bs.inputs["Alpha"])
        m.surface_render_method = "BLENDED"
        try:
            m.blend_method = "BLEND"
        except Exception:  # noqa: BLE001
            pass
    rr = nt.nodes.new("ShaderNodeTexImage")
    rr.image = load(t_r, False)
    nt.links.new(rr.outputs["Color"], bs.inputs["Roughness"])
    nn = nt.nodes.new("ShaderNodeTexImage")
    nn.image = load(t_n, False)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bs.inputs["Normal"])
    bs.inputs["Metallic"].default_value = metallic
    tex = [t_bc + ".png", t_n + ".png", t_n + "_DX.png", t_r + ".png"]
    if t_e:
        ee = nt.nodes.new("ShaderNodeTexImage")
        ee.image = load(t_e, True)
        nt.links.new(ee.outputs["Color"], bs.inputs["Emission Color"])
        bs.inputs["Emission Strength"].default_value = e_strength
        tex.append(t_e + ".png")
    m.use_backface_culling = not double
    m["textures"] = [t.replace("_N_DX.png", "_N_DX.png") for t in tex]
    m["emissive_strength"] = e_strength
    return m


def kit(name):
    return make_mat(name, f"T_{name[2:]}_BC", f"T_{name[2:]}_N", f"T_{name[2:]}_R")


MATS = {
    "M_Wood": kit("M_Wood"), "M_WoodTar": kit("M_WoodTar"), "M_Turf": kit("M_Turf"), "M_Stone": kit("M_Stone"),
    "M_Iron": make_mat("M_Iron", "T_Iron_BC", "T_Iron_N", "T_Iron_R", metallic=0.6),
    "M_Shields": make_mat("M_Shields_ClanA", "T_Shields_ClanA_BC", "T_Shields_N", "T_Shields_R"),
    "M_Shingle": make_mat("M_Shingle", "T_Shingle_BC", "T_Shingle_N", "T_Shingle_R"),
    "M_Rock": make_mat("M_Rock", "T_Rock_BC", "T_Rock_N", "T_Rock_R"),
    "M_RockFrost": make_mat("M_RockFrost", "T_RockFrost_BC", "T_Rock_N", "T_Rock_R"),
    "M_LavaRock": make_mat("M_LavaRock", "T_LavaRock_BC", "T_LavaRock_N", "T_LavaRock_R", "T_LavaRock_E", 4.0),
    "M_Obsidian": make_mat("M_Obsidian", "T_Obsidian_BC", "T_Obsidian_N", "T_Obsidian_R", "T_Obsidian_E", 5.0),
    "M_Crystal": make_mat("M_Crystal", "T_Crystal_BC", "T_Crystal_N", "T_Crystal_R", "T_Crystal_E", 1.5),
    "M_Bone": make_mat("M_Bone", "T_Bone_BC", "T_Bone_N", "T_Bone_R"),
    "M_Charred": make_mat("M_Charred", "T_Charred_BC", "T_Charred_N", "T_Charred_R", "T_Charred_E", 6.0),
    "M_Ice": make_mat("M_Ice", "T_Ice_BC", "T_Ice_N", "T_Ice_R", "T_Ice_E", 1.5),
    "M_Runes": make_mat("M_Runes", "T_Runes_BC", "T_Runes_N", "T_Runes_R", "T_Runes_E", 0.8),
    "M_Waterfall": make_mat("M_Waterfall", "T_Waterfall_BC", "T_Waterfall_N", "T_Waterfall_R", alpha=True, double=True),
    "M_Foam": make_mat("M_Foam", "T_Foam_BC", "T_Foam_N", "T_Foam_R", alpha=True, double=True),
}

ENTRIES = []   # (island, name, builder, note, extra)
STRONG, RUNE, LAIR, FALLS, COAST = "forest_isle_stronghold", "glacier_isle_rune_circle", "ember_isle_dragon_lair", \
    "forest_isle_waterfall", "coastal_all_islands"
ENTRIES += [
    (STRONG, "MeadHall", LP.build_mead_hall, "40 x 12 m carved mead hall, entrance porch at +X, side door +Y"),
    (STRONG, "Gatehouse", LP.build_gatehouse, "stone bastions + timber gate storey; wall line along Y, outside = +X"),
    (STRONG, "FortWall", lambda: LP.build_fort_wall(False),
     "rampart + palisade, 8 m along X, inside -Y, 16 subdivisions: use as Unreal SplineMesh to curve freely"),
    (STRONG, "FortWallCurve15", lambda: LP.build_fort_wall(True),
     "pre-bent 15 deg segment (R 30.6 m about (0,-R)); 24 = full ring, 22 + gatehouse leaves the gate gap"),
    (RUNE, "RuneCircle", LP.build_rune_circle, "assembled ring (R 9 m) of 7 runestones + altar"),
] + [(RUNE, f"Runestone_{c}", (lambda i=i: LP.build_runestone(i)), "single runestone; rune faces = +-Y")
     for i, c in enumerate("ABCD")] + [
    (RUNE, "RuneAltar", LP.build_altar, "altar slab on two stones"),
] + [(RUNE, f"FrostBoulder_{c}", (lambda i=i: LP.build_frost_boulder(i)), "frost-cracked boulder")
     for i, c in enumerate("ABC")] + [
    (RUNE, "IceShrine", LP.build_ice_shrine, "ice archway, passage along X, 7.2 m span"),
    (LAIR, "DragonNest", LP.build_nest, "21 m nest: charred timbers, bones, plundered shields, 3 glowing eggs"),
    (LAIR, "DragonSkull", LP.build_dragon_skull, "~7 m dragon skull, jaw open, facing +X"),
    (LAIR, "DragonRibs", LP.build_dragon_ribs, "half-buried spine + ribcage, 16 m"),
    (LAIR, "ObsidianSpires_A", lambda: LP.build_obsidian_spires(0), "obsidian spire cluster, tallest 14 m"),
    (LAIR, "ObsidianSpires_B", lambda: LP.build_obsidian_spires(1), "small obsidian spire cluster, 8 m"),
    (LAIR, "EmberCrystals", LP.build_crystal_cluster, "glowing ember crystal cluster on lava rock"),
] + [(LAIR, f"LavaRock_{c}", (lambda i=i: LP.build_lava_rock(i)), "lava rock with glowing cracks")
     for i, c in enumerate("ABC")] + [
    (FALLS, "FallsLip", LP.build_falls_lip, "rock lip with a channel notch; water flows +X over the crest"),
    (FALLS, "PlungeRocks", LP.build_plunge_rocks, "ring of boulders round the plunge pool, outflow open to +X; origin = pool level"),
    (FALLS, "WaterfallFoam", LP.build_waterfall_foam, "3 crossed mist cards + floating foam ring; origin = water level"),
    (COAST, "WreckBow", lambda: LP.build_wreck(True), "bow half of a wrecked longship, heeled 24 deg, buried 0.6 m"),
    (COAST, "WreckStern", lambda: LP.build_wreck(False), "stern half of a wrecked longship"),
    (COAST, "DriftwoodPile", LP.build_driftwood, "bleached driftwood pile"),
]

objs = {}
manifest = []


def bbox(ob):
    lo = [min(v.co[k] for v in ob.data.vertices) for k in range(3)]
    hi = [max(v.co[k] for v in ob.data.vertices) for k in range(3)]
    return [round(c, 3) for c in lo], [round(c, 3) for c in hi]


def mats_of(ob):
    return {m.name: list(m["textures"]) for m in ob.data.materials}


def add(island, name, mb, note, attach=None):
    t = time.time()
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    ob = mb.build(MATS, name=f"SM_{name}")
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll.objects.link(ob)
    objs[name] = ob
    lo, hi = bbox(ob)
    e = {"name": name, "island": island, "fbx": f"SM_{name}.fbx", "glb_node": f"SM_{name}", "note": note,
         "bbox_min_m": lo, "bbox_max_m": hi, "size_m": [round(h - l, 2) for l, h in zip(lo, hi)],
         "triangles": tri_count(ob), "materials": mats_of(ob)}
    if attach:
        e["attach_points"] = attach
    manifest.append(e)
    print(f"{name}: {e['triangles']} tris {time.time() - t:.1f}s")


for island, name, fn, note in ENTRIES:
    add(island, name, fn(), note)

# waterfall sheet (attach to the lip crest) and beacon (fire attach point)
lip = objs["FallsLip"]
cand = [v.co for v in lip.data.vertices if abs(v.co.y) < 1.0]
ztop = max(c.z for c in cand)
crest = max((c for c in cand if c.z > ztop - 1.5), key=lambda c: c.x)
crest = crest + type(crest)((0.3, 0.0, 0.1))
mb, top = LP.build_waterfall_sheet()
add(FALLS, "WaterfallSheet", mb,
    "falling-water sheet, 24 m drop (scale Z to fit). UV: U across, V = metres from bottom / 4; Panner on V "
    "(+0.3..0.6 /s) flows the water DOWN. Two-sided, translucent (BC alpha).",
    {"top_edge_local_m": list(top),
     "place_on_FallsLip": "put the sheet so its top_edge sits on FallsLip crest",
     "FallsLip_crest_m": [round(crest.x, 2), 0.0, round(crest.z, 2)]})
mb, fire = LP.build_beacon()
add(COAST, "BeaconTower", mb, "dry-stone beacon tower 9 m with iron fire basket (charred logs glow)",
    {"fire": {"location_m": list(fire), "note": "spawn the beacon fire / smoke Niagara here"}})

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "Landmarks.blend"), relative_remap=True)

FBX_SETTINGS = dict(use_selection=True, object_types={"MESH"}, apply_unit_scale=True,
                    apply_scale_options="FBX_SCALE_ALL", global_scale=1.0, axis_forward="-Z", axis_up="Y",
                    use_space_transform=True, bake_space_transform=False, mesh_smooth_type="FACE",
                    use_mesh_modifiers=True, use_tspace=True, add_leaf_bones=False, bake_anim=False,
                    path_mode="RELATIVE", embed_textures=False)
for name, ob in objs.items():
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, f"SM_{name}.fbx"), **FBX_SETTINGS)
print(f"fbx done {time.time() - T0:.1f}s")

for img in bpy.data.images:
    if img.size[0] > 1024:
        img.scale(1024, img.size[1] * 1024 // img.size[0])
bpy.ops.object.select_all(action="DESELECT")
for ob in objs.values():
    ob.select_set(True)
glb = os.path.join(OUT, "Landmarks.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_image_format="WEBP",
                          export_jpeg_quality=85, export_yup=True, export_apply=False)
size_mb = round(os.path.getsize(glb) / 1e6, 2)

mpath = os.path.join(OUT, "props_manifest.json")
M = json.load(open(mpath)) if os.path.exists(mpath) else {}
M["landmarks"] = {
    "glb": "Landmarks.glb", "glb_size_mb": size_mb,
    "glb_note": "named nodes, all at the origin; 1024 px textures (PNG kept for alpha / emissive).",
    "emissive": "*_E.png = emissive colour (sRGB). Suggested Unreal multipliers = materials' emissive_strength "
                "(lava 4, obsidian 5, crystal 1.5, charred 6, runes 0.8, ice 1.5).",
    "translucent_two_sided": ["M_Waterfall", "M_Foam"],
    "shared_from_kit": ["M_Wood", "M_WoodTar", "M_Turf", "M_Stone", "M_Iron", "M_Shields_ClanA"],
    "fbx_export_settings": {k: (sorted(v) if isinstance(v, set) else v) for k, v in FBX_SETTINGS.items()},
    "outside_assets": "none - procedural (tools/blender/world/landmark_*.py, build_landmarks.py)",
    "props": manifest,
}
json.dump(M, open(mpath, "w"), indent=1)
print(f"ALL DONE {time.time() - T0:.1f}s glb {size_mb} MB")
