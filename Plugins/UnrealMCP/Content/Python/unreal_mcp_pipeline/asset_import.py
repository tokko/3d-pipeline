"""
import_fbx_asset — FBX import handler (editor-side).

Uses unreal.AssetImportTask + unreal.FbxImportUI. LOD generation is a
post-import operation (the FBX importer has no single auto-LOD toggle).
"""

import os

import unreal


def import_fbx_asset(file_path, destination_path, asset_name,
                     skeleton_path="", auto_lods=True,
                     build_nanite=True, import_materials=False,
                     import_textures=False):
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"FBX not found on disk: {file_path}"}

    task = unreal.AssetImportTask()
    task.filename = file_path
    task.destination_path = destination_path
    task.destination_name = asset_name
    task.replace_existing = True
    task.automated = True
    task.save = True

    options = unreal.FbxImportUI()
    options.import_mesh = True
    options.import_textures = bool(import_textures)
    options.import_materials = bool(import_materials)
    options.import_as_skeletal = bool(skeleton_path)
    options.import_animations = bool(skeleton_path)
    options.create_physics_asset = bool(skeleton_path)

    if skeleton_path:
        skeleton = unreal.load_asset(skeleton_path)
        if not skeleton:
            return {"success": False, "error": f"skeleton not found: {skeleton_path}"}
        options.skeleton = skeleton

    norm = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    options.static_mesh_import_data.normal_import_method = norm
    options.skeletal_mesh_import_data.normal_import_method = norm
    options.static_mesh_import_data.build_nanite = bool(build_nanite)
    options.static_mesh_import_data.auto_generate_collision = True

    task.options = options

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    asset_tools.import_asset_tasks([task])

    paths = list(task.imported_object_paths or [])
    if not paths:
        return {"success": False, "error": "import returned no assets — check Output Log for FBX-side errors"}

    asset_path = paths[0]
    imported = unreal.load_asset(asset_path)
    if imported is None:
        return {"success": False, "error": f"imported asset path returned None: {asset_path}"}

    warnings = []
    if auto_lods and isinstance(imported, unreal.StaticMesh):
        try:
            _generate_static_lods(imported)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"auto_lods failed: {exc}")

    unreal.EditorAssetLibrary.save_asset(asset_path)

    return {
        "success": True,
        "asset_path": asset_path,
        "asset_class": type(imported).__name__,
        "warnings": warnings,
    }


def _generate_static_lods(mesh):
    """Generate three reduction LODs (50% / 25% / 12.5%) for a StaticMesh.

    UE 5.5's mesh-reduction Python surface has shifted across point releases;
    we use EditorStaticMeshLibrary.set_lods_with_notification when available
    and fall back to the older set_lods entry point. Either way, three
    reduction levels are added below LOD0 with auto-computed screen sizes.
    """
    library = unreal.EditorStaticMeshLibrary

    settings = []
    for percent, screen in [(0.5, 0.5), (0.25, 0.25), (0.125, 0.125)]:
        s = unreal.EditorScriptingMeshReductionSettings()
        s.percent_triangles = percent
        s.screen_size = screen
        settings.append(s)

    options = unreal.EditorScriptingMeshReductionOptions()
    options.reduction_settings = settings
    options.auto_compute_lod_screen_size = True

    if hasattr(library, "set_lods_with_notification"):
        library.set_lods_with_notification(mesh, options, True)
    else:
        library.set_lods(mesh, options)
