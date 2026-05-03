"""
Blender cleanup script invoked by /gen-asset between TRELLIS and Mixamo.

Reads a GLB, decimates to a target tri count, recenters to origin, scales
to a humanoid reference height (if --is_humanoid), triangulates, and FBX-
exports with textures referenced (not embedded — the slash command
manages textures separately and feeds them to UE5's assign_material).

Invoked by Blender MCP via:
    {"script": "<contents of this file>",
     "args": {"input_glb": "...", "output_fbx": "...",
              "is_humanoid": true, "target_height_cm": 180}}

Run directly for local testing:
    blender --background --python cleanup.py -- \\
        --input_glb input.glb --output_fbx out.fbx --is_humanoid

Targets Blender 4.0+. Triangle target is 32k — a sane upper bound for
TRELLIS output that still looks decent at character scale.
"""

import argparse
import sys

import bpy


_TARGET_TRIS = 32_000


def _parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_glb", required=True)
    parser.add_argument("--output_fbx", required=True)
    parser.add_argument("--is_humanoid", action="store_true")
    parser.add_argument("--target_height_cm", type=float, default=180.0)
    parser.add_argument("--target_tris", type=int, default=_TARGET_TRIS)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    return parser.parse_args(argv)


def _wipe_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _import_glb(path):
    bpy.ops.import_scene.gltf(filepath=path)


def _all_meshes():
    return [obj for obj in bpy.data.objects if obj.type == "MESH"]


def _join_meshes():
    meshes = _all_meshes()
    if len(meshes) <= 1:
        return meshes[0] if meshes else None
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def _recenter(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.location = (0.0, 0.0, 0.0)


def _scale_to_height(obj, target_height_cm):
    bbox = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not bbox:
        return
    zs = [v.z for v in bbox]
    height = max(zs) - min(zs)
    if height <= 0:
        return
    target = target_height_cm / 100.0  # blender units = m
    factor = target / height
    obj.scale = (obj.scale[0] * factor, obj.scale[1] * factor, obj.scale[2] * factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def _decimate(obj, target_tris):
    current = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if current <= target_tris:
        return
    ratio = target_tris / current
    mod = obj.modifiers.new(name="Decimate", type="DECIMATE")
    mod.ratio = max(0.01, min(1.0, ratio))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _triangulate(obj):
    mod = obj.modifiers.new(name="Triangulate", type="TRIANGULATE")
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def _align_t_pose(obj):
    """Best-effort T-pose alignment for humanoids.

    Mixamo expects the character facing +Y (or +X depending on docs you
    read), arms out to the sides, in T-pose. TRELLIS output is usually
    in some neutral pose facing -Z. This is a pragmatic rotation, not
    real pose-matching — enough to get past Mixamo's marker auto-detect
    in most cases. Manual fixup may still be needed for edge cases.
    """
    obj.rotation_euler = (0.0, 0.0, 0.0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)


def _export_fbx(path):
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=False,
        apply_unit_scale=True,
        bake_space_transform=True,
        path_mode="COPY",
        embed_textures=False,
        axis_forward="-Z",
        axis_up="Y",
    )


def main():
    args = _parse_args(sys.argv)
    _wipe_scene()
    _import_glb(args.input_glb)

    obj = _join_meshes()
    if obj is None:
        raise SystemExit("no mesh found in GLB")

    _recenter(obj)
    if args.is_humanoid:
        _align_t_pose(obj)
        _scale_to_height(obj, args.target_height_cm)
    _decimate(obj, args.target_tris)
    _triangulate(obj)
    _export_fbx(args.output_fbx)


if __name__ == "__main__":
    main()
