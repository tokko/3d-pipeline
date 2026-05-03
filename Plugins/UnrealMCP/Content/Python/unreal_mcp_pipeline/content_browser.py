"""
get_content_browser_assets — list assets under a content folder.
"""

import unreal


def get_content_browser_assets(folder_path, asset_type_filter=""):
    if not folder_path:
        return {"success": False, "error": "folder_path is required"}

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = registry.get_assets_by_path(folder_path, recursive=True)

    out = []
    for a in assets:
        # asset_class_path is FTopLevelAssetPath (UE5.1+); fall back to
        # the deprecated asset_class field if a stub or older engine
        # version is in use.
        cls = ""
        try:
            cls = str(a.asset_class_path.asset_name)
        except AttributeError:
            cls = str(getattr(a, "asset_class", ""))

        if asset_type_filter and cls != asset_type_filter:
            continue

        package = str(a.package_name)
        name = str(a.asset_name)
        out.append({
            "asset_path": f"{package}.{name}",
            "asset_class": cls,
            "package_name": package,
        })

    return {"success": True, "assets": out, "count": len(out)}
