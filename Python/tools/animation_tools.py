"""
Animation Tools for Unreal MCP (3d-pipeline fork).

Editor-side counterpart: animation_wire.wire_animation_blueprint
                         stretch.compile_anim_blueprint
"""

import logging
import os
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP, Context

from tools.asset_tools import _unwrap

logger = logging.getLogger("UnrealMCP")

# Defaults sourced from the UE5 Manny project; override per-deployment via env.
_DEFAULT_MANNEQUIN_SKELETON = os.environ.get(
    "UE_MANNEQUIN_SKELETON",
    "/Game/Characters/Mannequins/Meshes/SK_Mannequin_Skeleton",
)
_DEFAULT_MANNEQUIN_IK_RIG = os.environ.get(
    "UE_MANNEQUIN_IK_RIG",
    "/Game/Characters/Mannequins/Rigs/IK_Mannequin",
)


def register_animation_tools(mcp: FastMCP):
    """Register animation-blueprint and retargeting tools with the MCP server."""

    @mcp.tool()
    def wire_animation_blueprint(
        ctx: Context,
        skeletal_mesh_path: str,
        anim_blueprint_path: str = "create_default",
        retarget_to_mannequin: bool = True,
        target_skeleton_path: str = _DEFAULT_MANNEQUIN_SKELETON,
        target_ik_rig_path: str = _DEFAULT_MANNEQUIN_IK_RIG,
    ) -> Dict[str, Any]:
        """Wire a skeletal mesh to an Animation Blueprint, optionally retarget to UE5 Manny.

        anim_blueprint_path:
          - "create_default": create ABP_<MeshName> next to the mesh
          - any /Game/... path: assign that existing AnimBP to the mesh

        retarget_to_mannequin is best-effort. UE5's IK Retargeter requires a
        source IK Rig, which arbitrary TRELLIS-derived skeletons do not have.
        If a source rig is found at <mesh_dir>/IK_<name>, retargeting runs;
        otherwise the response includes retargeted=False with a reason.
        Never silently fakes a successful retarget.
        """
        from unreal_mcp_server import get_unreal_connection

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("wire_animation_blueprint", {
            "skeletal_mesh_path": skeletal_mesh_path,
            "anim_blueprint_path": anim_blueprint_path,
            "retarget_to_mannequin": retarget_to_mannequin,
            "target_skeleton_path": target_skeleton_path,
            "target_ik_rig_path": target_ik_rig_path,
        })
        return _unwrap(response)

    @mcp.tool()
    def compile_anim_blueprint(
        ctx: Context,
        anim_blueprint_path: str,
    ) -> Dict[str, Any]:
        """Compile an Animation Blueprint. Required after structural changes
        before the AnimBP can be assigned to a SkeletalMeshComponent."""
        from unreal_mcp_server import get_unreal_connection

        unreal = get_unreal_connection()
        if not unreal:
            return {"success": False, "error": "could not connect to Unreal Engine"}

        response = unreal.send_command("compile_anim_blueprint", {
            "anim_blueprint_path": anim_blueprint_path,
        })
        return _unwrap(response)
