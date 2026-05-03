"""
Scene Tools for Unreal MCP (3d-pipeline fork).

Editor-side counterpart: scene_place.batch_place_actors
"""

import logging
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP, Context

from tools.asset_tools import _unwrap

logger = logging.getLogger("UnrealMCP")


def register_scene_tools(mcp: FastMCP):
    """Register batch placement tools with the MCP server."""

    @mcp.tool()
    def batch_place_actors(
        ctx: Context,
        manifest_path: str,
        level_path: str = "",
        save_level: bool = True,
    ) -> Dict[str, Any]:
        """Spawn many actors from a JSON manifest into a level.

        Manifest schema (one entry per actor):
            {
              "actors": [
                {
                  "asset_path": "/Game/Characters/DemonKnight",
                  "name": "DemonKnight_01",
                  "location": [x, y, z],
                  "rotation": [pitch, yaw, roll],
                  "scale":    [sx, sy, sz],
                  "tags":     ["enemy", "melee"]
                }, ...
              ]
            }

        Wrapped in a single editor undo transaction so ctrl-Z reverts the
        whole batch. save_level=False is for advanced use; the default
        matches the slash-command pipeline's expectation that the level is
        persisted after placement.
        """
        from unreal_mcp_server import get_unreal_connection

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("batch_place_actors", {
            "manifest_path": manifest_path,
            "level_path": level_path,
            "save_level": save_level,
        })
        return _unwrap(response)
