---
description: List all imported assets in the current UE5 project, grouped by category
allowed-tools: mcp__unreal_mcp__get_content_browser_assets
---

# Asset status

Snapshot of every asset Claude has imported into the project's content
browser. Useful before a `/gen-asset` run to avoid duplicates, and as a
sanity check that the MCP server is actually reaching the editor.

## Steps

1. For each folder, call MCP tool `get_content_browser_assets`:
   - `/Game/SiblingGame/Characters/`
   - `/Game/SiblingGame/Environment/`
   - `/Game/SiblingGame/Props/`
   - `/Game/SiblingGame/Materials/`
   - `/Game/SpaceGame/` (placeholder for future game two)

2. For each result, group entries by `asset_class` (SkeletalMesh,
   StaticMesh, MaterialInstanceConstant, AnimBlueprint, ...).

3. Print a markdown summary:
   ```
   ## /Game/SiblingGame/Characters/
   - SkeletalMesh (3): DemonKnight, FireImp, ...
   - AnimBlueprint (3): ABP_DemonKnight, ...

   ## /Game/SiblingGame/Props/
   - StaticMesh (12): IronAnvil, BrokenSword, ...
   ```

4. End with a totals line: `Total: <n> assets across <m> folders`.

5. If any folder returns `success=False`, list it under a "Failed
   folders" heading with the error message — don't fail the whole
   command.
