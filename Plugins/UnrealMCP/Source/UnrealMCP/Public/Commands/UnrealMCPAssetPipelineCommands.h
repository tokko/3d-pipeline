#pragma once

#include "CoreMinimal.h"
#include "Json.h"

/**
 * Handler class for asset-pipeline MCP commands (3d-pipeline fork).
 *
 * Forwards each command to the editor's Python interpreter via
 * IPythonScriptPlugin, where the real implementation lives in
 * Plugins/UnrealMCP/Content/Python/. The Python handler writes its JSON
 * result to a temp file whose path is injected into the script; this side
 * reads + unlinks it. No log scraping.
 *
 * Handles: import_fbx_asset, assign_material, wire_animation_blueprint,
 * batch_place_actors, get_content_browser_assets, plus stretch tools
 * (delete_asset, rename_asset, save_all_dirty, compile_anim_blueprint).
 */
class UNREALMCP_API FUnrealMCPAssetPipelineCommands
{
public:
    FUnrealMCPAssetPipelineCommands();

    TSharedPtr<FJsonObject> HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params);

    // Returns true if the named command is one we own.
    static bool OwnsCommand(const FString& CommandType);

private:
    // Default 300s (5 minutes) — long imports with LOD generation can run
    // longer than the upstream commands ever do. Override via env var
    // UE_MCP_HANDLER_TIMEOUT_SEC.
    double GetHandlerTimeoutSeconds() const;
};
