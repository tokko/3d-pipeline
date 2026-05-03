---
description: Place an existing content-browser asset into the current level
argument-hint: <asset_path> [x y z] [pitch yaw roll] [sx sy sz]
allowed-tools: Bash, Write, mcp__unreal_mcp__batch_place_actors
---

# Place asset in level

Thin wrapper around `batch_place_actors` for the single-actor case. Useful
when you've imported an asset via `/gen-asset` and want it dropped into
the active level without writing a manifest by hand.

**Args:** $ARGUMENTS

Parse `$ARGUMENTS` as `<asset_path> [location] [rotation] [scale]`.
Defaults: location `[0,0,0]`, rotation `[0,0,0]`, scale `[1,1,1]`.

## Steps

1. Build a manifest dict:
   ```json
   {
     "actors": [
       {
         "asset_path": "<asset_path>",
         "name": "<basename of asset_path>_placed",
         "location": [x, y, z],
         "rotation": [pitch, yaw, roll],
         "scale":    [sx, sy, sz],
         "tags":     ["mcp_placed"]
       }
     ]
   }
   ```

2. Write to a temp file at `${TMPDIR:-/tmp}/place-asset-<timestamp>.json`.

3. Call MCP tool `batch_place_actors(manifest_path=<tmp>, save_level=True)`.

4. Report the placed actor's label and the level path back to the user.

5. Delete the temp manifest file.
