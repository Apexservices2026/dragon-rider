"""Export the baked dragon + rider for Unreal (FBX) and three.js (GLB).

Run (after build_dragon.py and build_rider.py):
  blender -b --factory-startup --python-exit-code 1 -P tools/blender/dragon/export.py

FBX (Unreal 5): +X forward / Z up in Unreal, 1 m = 100 cm.
  axis_forward='-Z', axis_up='Y' (Blender defaults; Blender (x, y, z) m -> Unreal (x, -y, z) cm),
  apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', global_scale=1.0,
  add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X', all bones (incl. non-deform
  Saddle), mesh triangulated + tangent space, every action baked as its own take (step 1, no simplify).
  Textures are referenced relatively from ./Textures (PNG).
GLB: Y-up glTF, all actions as separate clips, textures down-sized and JPEG-encoded to stay small.
"""
import os
import sys
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlib  # noqa: E402

OUT = dlib.OUT_DIR

FBX_KW = dict(
    use_selection=True, object_types={'ARMATURE', 'MESH'}, global_scale=1.0, apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_UNITS', axis_forward='-Z', axis_up='Y', use_space_transform=True,
    bake_space_transform=False, use_mesh_modifiers=True, mesh_smooth_type='FACE', use_triangles=True,
    use_tspace=True, add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X',
    use_armature_deform_only=False, armature_nodetype='NULL', bake_anim=True,
    bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=True,
    bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0,
    path_mode='RELATIVE', embed_textures=False)

# glb texture sizes (longest side) per map kind
GLB_SIZE = {"BaseColor": 2048, "Normal": 2048, "ORM": 1024, "Emissive": 1024}


def select_only(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_asset(blend, arm_name, mesh_name, base, glb_overrides=None):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, blend))
    arm = bpy.data.objects[arm_name]
    mesh = bpy.data.objects[mesh_name]
    # rest pose / no active action so the bind pose is clean
    arm.animation_data.action = None
    bpy.context.scene.frame_set(0)
    select_only([arm, mesh])
    fbx = os.path.join(OUT, base + ".fbx")
    bpy.ops.export_scene.fbx(filepath=fbx, **FBX_KW)
    print("FBX", fbx, os.path.getsize(fbx) // 1024, "KB")
    # ---- glb: down-size the textures in memory
    sizes = dict(GLB_SIZE, **(glb_overrides or {}))
    for img in bpy.data.images:
        for k, s in sizes.items():
            if img.name.endswith(k + ".png") or img.name.endswith(k):
                if img.size[0] > s:
                    img.scale(s, s)
    select_only([arm, mesh])
    glb = os.path.join(OUT, base + ".glb")
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format='GLB', use_selection=True, export_yup=True,
        export_apply=False, export_texcoords=True, export_normals=True, export_tangents=False,
        export_materials='EXPORT', export_image_format='JPEG', export_jpeg_quality=82,
        export_skins=True, export_all_influences=False, export_animations=True,
        export_animation_mode='ACTIONS', export_frame_range=False, export_force_sampling=True,
        export_anim_single_armature=True, export_reset_pose_bones=True, export_optimize_animation_size=True)
    print("GLB", glb, os.path.getsize(glb) // 1024, "KB")
    return fbx, glb


export_asset("Dragon.blend", "DragonRig", "Dragon", "Dragon",
             {"Wings_Normal": 1024})
if os.path.exists(os.path.join(OUT, "Rider.blend")):
    export_asset("Rider.blend", "RiderRig", "Rider", "Rider", {"Rider_BaseColor": 2048})
