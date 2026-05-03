"""
Stretch tools — delete_asset, rename_asset, save_all_dirty, compile_anim_blueprint.

The pipeline hits all four during normal iteration. They live in one
module because none of them justifies its own file.
"""

import unreal


def delete_asset(asset_path, confirm=False):
    if not confirm:
        return {"success": False, "error": "delete_asset requires confirm=True"}
    if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        return {"success": False, "error": f"asset does not exist: {asset_path}"}
    ok = unreal.EditorAssetLibrary.delete_asset(asset_path)
    return {"success": bool(ok), "asset_path": asset_path}


def rename_asset(asset_path, new_name):
    if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        return {"success": False, "error": f"asset does not exist: {asset_path}"}

    package = asset_path.split(".", 1)[0]
    folder, _, _ = package.rpartition("/")
    new_path = f"{folder}/{new_name}"
    ok = unreal.EditorAssetLibrary.rename_asset(asset_path, new_path)
    return {"success": bool(ok), "asset_path": asset_path, "new_asset_path": new_path}


def save_all_dirty():
    saved = unreal.EditorAssetLibrary.save_directory(
        "/Game", recursive=True, only_if_is_dirty=True)
    return {"success": bool(saved)}


def compile_anim_blueprint(anim_blueprint_path):
    abp = unreal.load_asset(anim_blueprint_path)
    if abp is None:
        return {"success": False, "error": f"AnimBP not found: {anim_blueprint_path}"}
    if not isinstance(abp, unreal.AnimBlueprint):
        return {"success": False,
                "error": f"asset is not an AnimBlueprint: {type(abp).__name__}"}
    # KismetEditorUtilities is the C++ entry point; the Python surface is
    # the BlueprintEditorLibrary.compile_blueprint shortcut.
    unreal.BlueprintEditorLibrary.compile_blueprint(abp)
    unreal.EditorAssetLibrary.save_asset(anim_blueprint_path)
    return {"success": True, "asset_path": anim_blueprint_path}
