"""Re-import the exported FBX / GLB files and print what a consumer will see.

Run:  blender -b --factory-startup -P tools/blender/dragon/verify_export.py
"""
import os
import sys
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlib  # noqa: E402


def report(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path, use_anim=True)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    tris = 0
    for m in meshes:
        m.data.calc_loop_triangles()
        tris += len(m.data.loop_triangles)
    print(f"== {os.path.basename(path)}  {os.path.getsize(path) / 1e6:.1f} MB")
    for a in arms:
        dims = a.dimensions
        print(f"   armature {a.name} bones={len(a.data.bones)} scale={tuple(round(s, 3) for s in a.scale)}")
    for m in meshes:
        bb = [m.matrix_world @ __import__('mathutils').Vector(c) for c in m.bound_box]
        xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
        print(f"   mesh {m.name} tris={len(m.data.loop_triangles)} mats={[s.material.name for s in m.material_slots if s.material]}"
              f" bbox x[{min(xs):.2f},{max(xs):.2f}] y[{min(ys):.2f},{max(ys):.2f}] z[{min(zs):.2f},{max(zs):.2f}]")
    for act in bpy.data.actions:
        fr = act.frame_range
        print(f"   action {act.name}: frames {fr[0]:.0f}-{fr[1]:.0f}")
    print(f"   total tris {tris}")


for f in ("Dragon.fbx", "Rider.fbx", "Dragon.glb", "Rider.glb", "DragonRider.glb"):
    p = os.path.join(dlib.OUT_DIR, f)
    if os.path.exists(p):
        report(p)
