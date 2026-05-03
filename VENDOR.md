# Vendoring

This repository is a fork-and-extend of [`chongdashu/unreal-mcp`][upstream]
(MIT, declared in upstream's README — upstream does not commit a `LICENSE`
file). The upstream snapshot was imported as a single squashed commit and
restructured to make the plugin droppable into any UE5 project.

[upstream]: https://github.com/chongdashu/unreal-mcp

## Pinned snapshot

| Field          | Value                                       |
|----------------|---------------------------------------------|
| Source         | https://github.com/chongdashu/unreal-mcp    |
| Branch         | `main`                                      |
| Commit         | `4e5f00da50733190481311e254d16d137a84ef33`  |
| Date pulled    | 2026-05-03                                  |
| License        | MIT (declared in upstream README)           |

## Restructure performed during vendoring

Upstream ships the C++ plugin nested inside its own sample `MCPGameProject/`.
We moved it to the repo root so other UE5 projects can depend on it:

```
upstream:    MCPGameProject/Plugins/UnrealMCP/
this fork:   Plugins/UnrealMCP/
```

`MCPGameProject/MCPGameProject.uproject` was modified to add
`AdditionalPluginDirectories: ["../Plugins"]` so the sample project keeps
working as a smoke-test harness.

## Refreshing from upstream

```bash
git remote add upstream https://github.com/chongdashu/unreal-mcp.git   # if missing
git fetch upstream main
git diff upstream/main -- Plugins/UnrealMCP/Source/  # see what changed
# Cherry-pick or hand-merge as needed; we do NOT auto-merge upstream into our line.
```

After any refresh, re-verify:

1. `Plugins/UnrealMCP/UnrealMCP.uplugin` still has our additions
   (`PythonPath`, `PythonScriptPlugin` dep, `EngineVersion`).
2. `UnrealMCP.Build.cs` still lists `PythonScriptPlugin` and `AssetTools`.
3. `UnrealMCPBridge.cpp` still constructs `AssetPipelineCommands` and
   routes via `FUnrealMCPAssetPipelineCommands::OwnsCommand`.

Then bump the SHA above and commit.

## Regenerating `M_PBR_Master`

The PBR master material at
`Plugins/UnrealMCP/Content/Materials/M_PBR_Master.uasset` is binary and
must be authored in the UE5 editor. To regenerate from scratch:

1. In any UE5.5 project with the UnrealMCP plugin enabled, create a new
   material at `/UnrealMCP/Materials/M_PBR_Master`.
2. Add four texture parameters: `Albedo` (BaseColor),
   `Normal` (NormalMap), `Roughness` (scalar from R channel),
   `Metallic` (scalar from R channel).
3. Add an additional `ORM` texture parameter and a static-switch
   parameter `UseORM`. When `UseORM=True`, route the ORM texture's R/G/B
   channels into AmbientOcclusion / Roughness / Metallic respectively
   (TRELLIS-native packing).
4. Save the asset, copy `M_PBR_Master.uasset` from the project's
   `Saved/` or `Content/UnrealMCP/Materials/` into this repo's
   `Plugins/UnrealMCP/Content/Materials/`.
5. Commit with a note describing what changed.

## Why squashed snapshot rather than submodule or full history?

Submodules make it impossible to edit upstream files in place — we need
to. Full history would pollute our log with hundreds of commits unrelated
to the asset pipeline. The squashed-snapshot approach lets us hand-merge
upstream improvements when they're worth the friction, without bleeding
upstream noise into our own commit history.
