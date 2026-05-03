"""
Editor-side asset-pipeline package for the UnrealMCP plugin.

The C++ dispatcher (Plugins/UnrealMCP/Source/UnrealMCP/Private/Commands/
UnrealMCPAssetPipelineCommands.cpp) imports this package and calls
dispatch_to_file(command, params_json, result_path). All real Unreal
Python API work happens in the per-domain modules under this package.

This module is loaded inside the UE5 editor's embedded Python interpreter
via the plugin's PythonPath descriptor entry. It is NOT importable from
the standalone MCP server process.
"""

from ._runtime import dispatch_to_file

__all__ = ["dispatch_to_file"]
