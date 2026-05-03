"""
Asset Tools for Unreal MCP (3d-pipeline fork).

Forwards FBX import and content-browser introspection commands to the
editor-side Python handlers in Plugins/UnrealMCP/Content/Python/.

These wrappers are deliberately thin — all real logic (Unreal Python API
calls) lives in the editor. Param shapes here MUST match the editor-side
handler signatures; drift between the two is the most common bug source
when adding tools.

Editor-side counterparts:
    asset_import.import_fbx_asset
    content_browser.get_content_browser_assets
Stretch tools:
    stretch.delete_asset
    stretch.rename_asset
    stretch.save_all_dirty
"""

import logging
from typing import Dict, List, Any
from mcp.server.fastmcp import FastMCP, Context

logger = logging.getLogger("UnrealMCP")


def register_asset_tools(mcp: FastMCP):
    """Register asset import + content-browser tools with the MCP server."""

    @mcp.tool()
    def import_fbx_asset(
        ctx: Context,
        file_path: str,
        destination_path: str,
        asset_name: str,
        skeleton_path: str = "",
        auto_lods: bool = True,
        build_nanite: bool = True,
        import_materials: bool = False,
        import_textures: bool = False,
    ) -> Dict[str, Any]:
        """Import an FBX file into the UE5 content browser.

        If skeleton_path is provided the FBX is imported as a SkeletalMesh
        bound to that skeleton; otherwise as a StaticMesh. Materials and
        textures are NOT imported by default — they are owned by the
        downstream assign_material tool to avoid duplicate/garbage assets.
        Pass build_nanite=False for TRELLIS-derived (non-manifold) meshes.
        """
        from unreal_mcp_server import get_unreal_connection

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("import_fbx_asset", {
            "file_path": file_path,
            "destination_path": destination_path,
            "asset_name": asset_name,
            "skeleton_path": skeleton_path,
            "auto_lods": auto_lods,
            "build_nanite": build_nanite,
            "import_materials": import_materials,
            "import_textures": import_textures,
        })
        return _unwrap(response)

    @mcp.tool()
    def get_content_browser_assets(
        ctx: Context,
        folder_path: str,
        asset_type_filter: str = "",
    ) -> Dict[str, Any]:
        """List assets in a content browser folder, optionally filtered by class.

        folder_path uses the engine's /Game/... convention. asset_type_filter
        matches against the asset class short name, e.g. "SkeletalMesh",
        "StaticMesh", "MaterialInstanceConstant".
        """
        from unreal_mcp_server import get_unreal_connection

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine", "assets": []}

        response = unreal.send_command("get_content_browser_assets", {
            "folder_path": folder_path,
            "asset_type_filter": asset_type_filter,
        })
        return _unwrap(response)

    @mcp.tool()
    def delete_asset(
        ctx: Context,
        asset_path: str,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """Delete an asset from the content browser. Irreversible.

        Refuses to act unless confirm=True. UE has no asset-deletion undo;
        the confirm flag is a deliberate guard against accidental wipes.
        """
        from unreal_mcp_server import get_unreal_connection

        if not confirm:
            return {"success": False, "error": "delete_asset requires confirm=True (irreversible)"}

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("delete_asset", {
            "asset_path": asset_path,
            "confirm": confirm,
        })
        return _unwrap(response)

    @mcp.tool()
    def rename_asset(
        ctx: Context,
        asset_path: str,
        new_name: str,
    ) -> Dict[str, Any]:
        """Rename an asset in place. Updates redirectors automatically."""
        from unreal_mcp_server import get_unreal_connection

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("rename_asset", {
            "asset_path": asset_path,
            "new_name": new_name,
        })
        return _unwrap(response)

    @mcp.tool()
    def save_all_dirty(ctx: Context) -> Dict[str, Any]:
        """Save every dirty asset under /Game. Use after a batch of mutating tools."""
        from unreal_mcp_server import get_unreal_connection

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("save_all_dirty", {})
        return _unwrap(response)


def _unwrap(response: Any) -> Dict[str, Any]:
    """Pull the payload out of the bridge envelope.

    The C++ bridge wraps editor-side responses as {"status": "success",
    "result": {...}} on success or {"status": "error", "error": "..."}
    on failure. The asset-pipeline handlers already conform to
    {"success": bool, ...}, so we want the inner result dict back.
    """
    if not isinstance(response, dict):
        return {"success": False, "error": f"unexpected response type: {type(response).__name__}"}
    if response.get("status") == "error":
        return {"success": False, "error": response.get("error", "unknown error")}
    if "result" in response and isinstance(response["result"], dict):
        return response["result"]
    return response
