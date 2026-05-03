"""
Material Tools for Unreal MCP (3d-pipeline fork).

Editor-side counterpart: material_assign.assign_material
"""

import logging
from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP, Context

from tools.asset_tools import _unwrap

logger = logging.getLogger("UnrealMCP")


def register_material_tools(mcp: FastMCP):
    """Register material-assignment tools with the MCP server."""

    @mcp.tool()
    def assign_material(
        ctx: Context,
        asset_path: str,
        material_path: str = "",
        texture_paths: Optional[Dict[str, str]] = None,
        orm_path: str = "",
        master_material_path: str = "/UnrealMCP/Materials/M_PBR_Master",
        slot_index: int = 0,
        replace_existing: bool = True,
    ) -> Dict[str, Any]:
        """Assign a material to a mesh.

        Two modes:
        - material_path mode: assigns an existing material asset to the mesh.
        - texture_paths mode: creates (or upserts) a MaterialInstanceConstant
          parented to master_material_path, wires the named texture parameters
          (Albedo / Normal / Roughness / Metallic / ORM), then assigns it.

        TRELLIS textures arrive as albedo + normal + ORM (occlusion/roughness/
        metallic packed in RGB). Pass orm_path for that case; the master
        material's static switch picks ORM mode.
        """
        from unreal_mcp_server import get_unreal_connection

        if not material_path and not texture_paths and not orm_path:
            return {"success": False, "error": "must provide either material_path, texture_paths, or orm_path"}

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("assign_material", {
            "asset_path": asset_path,
            "material_path": material_path,
            "texture_paths": texture_paths or {},
            "orm_path": orm_path,
            "master_material_path": master_material_path,
            "slot_index": slot_index,
            "replace_existing": replace_existing,
        })
        return _unwrap(response)
