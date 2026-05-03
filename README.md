# 3d-pipeline — UE5 MCP server for the TRELLIS → Blender → UE5 asset workflow

Self-hosted Model Context Protocol server that drives an end-to-end game
asset pipeline. Forked from [`chongdashu/unreal-mcp`][upstream] (MIT) and
extended with the asset-import, material-assignment, batch-placement,
content-browser, and animation-wiring tools that the original was missing.

[upstream]: https://github.com/chongdashu/unreal-mcp

```
TRELLIS (local, free) → Blender MCP → Mixamo (humanoids) → UE5 MCP (this) → game
```

The point: Claude Code can run `/gen-asset "scarred demon soldier"` and a
rigged, textured asset lands in the UE5 content browser without human
intervention.

## What this fork adds over upstream

| Tool                          | What it does                                                      |
|-------------------------------|-------------------------------------------------------------------|
| `import_fbx_asset`            | Headless FBX import (static or skeletal), auto-LODs, no-Nanite override for non-manifold meshes. |
| `assign_material`             | Assigns an existing material OR upserts a `MaterialInstanceConstant` from PBR textures (incl. ORM-packed). |
| `wire_animation_blueprint`    | Creates a default AnimBP next to the mesh, optional best-effort retarget to UE5 Manny. |
| `batch_place_actors`          | Spawns many actors from a JSON manifest in one undo transaction.  |
| `get_content_browser_assets`  | Lists assets under a folder, optionally filtered by class.        |
| `delete_asset` / `rename_asset` / `save_all_dirty` / `compile_anim_blueprint` | Stretch tools the pipeline hits in normal use. |

Plus three Claude Code slash commands under `claude_commands/`:

- `/gen-asset` — full text-prompt → rigged-mesh pipeline
- `/place-asset` — single-actor placement helper
- `/asset-status` — list everything in the project

## Architecture

The new tools follow the upstream convention but with a single twist: a
single new C++ command class (`UnrealMCPAssetPipelineCommands`) routes
each new command to editor-side Python via `IPythonScriptPlugin`. This
keeps the rich `unreal` Python API in play (FBX import, material instance
upsert, IK retargeter) without writing another half-dozen C++ command
classes.

```
Claude Code
    ↓ MCP (stdio)
Python/unreal_mcp_server.py        ← FastMCP, registers all tools
    ↓ TCP 127.0.0.1:55557
Plugins/UnrealMCP/Source/...       ← C++ bridge, dispatches by command name
    ↓ IPythonScriptPlugin (for new tools only)
Plugins/UnrealMCP/Content/Python/  ← editor-side handlers, write JSON to temp file
    ↓ JSON read + unlink
back up the stack
```

C++ ↔ Python IPC uses a temp-file JSON convention (path injected into the
script, handler writes, C++ reads + unlinks). No log scraping. 5min
default timeout, override with `UE_MCP_HANDLER_TIMEOUT_SEC`.

## Prerequisites

- **Unreal Engine 5.5** (pinned via `EngineVersion` in `.uplugin`)
- **Python 3.10+** (3.12 recommended)
- **`uv`** for Python env management
- The editor's **PythonScriptPlugin** must be enabled — the `.uplugin`
  declares it as a dependency, so first project load auto-prompts.

## Install

### 1. Drop the plugin into your UE5 project

```bash
# from your UE5 project root
cp -r /path/to/3d-pipeline/Plugins/UnrealMCP Plugins/UnrealMCP
# Windows: prefer a junction over a copy if you want to track this repo:
#   mklink /J Plugins\UnrealMCP C:\path\to\3d-pipeline\Plugins\UnrealMCP
```

Open the project. Editor will prompt to enable PythonScriptPlugin and
build the `UnrealMCP` module — accept both. The plugin's
`Content/Python/` directory is added to the editor's Python path
automatically via the `.uplugin` `PythonPath` field.

### 2. Set up the Python MCP server

```bash
cd 3d-pipeline/Python
uv sync
```

### 3. Wire it up in Claude Code

Copy `mcp.example.json` into `~/.claude/mcp.json` (or merge with your
existing one), edit the absolute path under `args[1]`, and restart
Claude Code.

### 4. Install the slash commands

```bash
cp claude_commands/*.md ~/.claude/commands/
```

Windows: `copy claude_commands\*.md %USERPROFILE%\.claude\commands\`

### 5. First-time setup tasks (one-off, must happen on Windows)

These can't be performed from a Linux dev box — they require the editor.

**a. Create the master material `M_PBR_Master`.** The `assign_material`
tool's texture-upsert mode parents instances to this material, and it's
not committed (UAssets aren't authorable from Linux). In the editor:

1. Right-click `Plugins/UnrealMCP Content/Materials/` → New Material
2. Name it `M_PBR_Master`
3. Add `Texture2DParameter` nodes named exactly `Albedo`, `Normal`, `ORM`
   (and optionally `Emissive`)
4. Wire `Albedo` → BaseColor, `Normal` → Normal, then split `ORM` RGB
   channels: R → AmbientOcclusion, G → Roughness, B → Metallic
5. Save. The plugin path resolves to `/UnrealMCP/Materials/M_PBR_Master`
   automatically.

**b. One-time Mixamo login.** First run of `mixamo_client.py rig` opens
a browser for Adobe IMS auth and caches the token at
`~/.mixamo/token.json` (override path with `MIXAMO_TOKEN_PATH`). The
token survives subsequent runs until refresh fails (~30 days).

**c. Set environment variables** (shell profile or `mcp.json` `env` block):

```
TRELLIS_ENDPOINT       e.g. http://localhost:8188
BLENDER_MCP_ENDPOINT   e.g. http://localhost:9876
STAGING_DIR            e.g. D:/AssetPipeline/staging
EXPORT_DIR             e.g. D:/AssetPipeline/export
STATE_DIR              e.g. D:/AssetPipeline/state
MIXAMO_TOKEN_PATH      ~/.mixamo/token.json
TELEGRAM_BOT_TOKEN     <bot token>
TELEGRAM_CHAT_ID       <chat id>
UNREAL_CONTENT_ROOT    /Game/SiblingGame
```

## Boot order (matters — the server fails confusingly without it)

1. **Open project in UE5.** Wait for the Output Log to show
   `UnrealMCPBridge: Server started on 127.0.0.1:55557`.
2. **Confirm PythonScriptPlugin is loaded.** Output Log should not warn
   about missing Python.
3. **Start Claude Code.** It launches the MCP server which connects to
   the editor. The MCP tool list should include `import_fbx_asset` and
   the others.

## Configuration via environment

| Var                            | Default       | Used by             |
|--------------------------------|---------------|---------------------|
| `UNREAL_MCP_HOST`              | `127.0.0.1`   | Python client       |
| `UNREAL_MCP_PORT`              | `55557`       | Python + C++ both   |
| `UE_MCP_CLIENT_TIMEOUT_SEC`    | `300`         | Python client       |
| `UE_MCP_HANDLER_TIMEOUT_SEC`   | `300`         | C++ handler         |
| `UE_MANNEQUIN_SKELETON`        | (UE5 default) | `wire_animation_blueprint` |
| `UE_MANNEQUIN_IK_RIG`          | (UE5 default) | `wire_animation_blueprint` |

Slash commands additionally read `TRELLIS_ENDPOINT`,
`BLENDER_MCP_ENDPOINT`, `MIXAMO_TOKEN_PATH`, `STAGING_DIR`, `EXPORT_DIR`,
`STATE_DIR`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. See
`claude_commands/gen-asset.md` for the full table.

## Daily workflow with Claude Code

Once the editor is open and Claude Code has connected to the MCP, you
have three modes of use:

**1. Slash commands for canned pipelines.**

```
/gen-asset "scarred demon soldier in plate armor"
/gen-asset --resume <asset_id>          # if a previous run failed mid-pipeline
/place-asset <path/to/manifest.json>    # batch-place actors with single-undo
/asset-status                           # content-browser snapshot — useful first turn of any session
```

`/gen-asset` runs end-to-end (TRELLIS → Blender → Mixamo if humanoid →
UE5 import → materials → optional AnimBP → Telegram ping). Checkpoints
to `${STATE_DIR}/<asset_id>.json` after every step, so any failure is
resumable.

**2. Direct natural-language asks** — once the MCP is connected, Claude
can call `import_fbx_asset`, `assign_material`, `wire_animation_blueprint`,
`batch_place_actors`, `get_content_browser_assets`, etc. as part of any
conversation. Examples that work without a slash command:

- "Import `D:/exports/tombstone_03.fbx` as a static mesh under
  `/Game/SiblingGame/Props/Cemetery` and assign material `M_Stone_Mossy`."
- "List every skeletal mesh under `/Game/SiblingGame/Characters` and
  give each a default AnimBP."
- "Lay out 30 tombstones on a 6×5 grid centred at the origin, random
  yaw, random scale 0.8–1.2."

**3. As building blocks in larger refactors.** Material swaps across
many actors, AnimBP regeneration after a skeleton change, content-
browser audits before a perf pass — all reachable from prompts.

The slash commands depend on:
- `claude_commands/mixamo_client.py` — Mixamo HTTP client (community
  reverse-engineered API; expect occasional breakage).
- `claude_commands/blender_scripts/cleanup.py` — invoked by Blender MCP
  to decimate, recenter, scale, and FBX-export TRELLIS GLB output.

## Verification

```bash
make smoke-list          # sanity check — server registers all tools (no editor needed)
make smoke               # full run — needs editor open with plugin loaded
```

**First-day verification on Windows** — run these in order, stop at the
first failure:

1. `make smoke-list` — server registers all tools, no editor needed.
2. Open UE5; `import_fbx_asset` of a hand-exported cube via the MCP
   inspector. Confirm it lands in the content browser.
3. `get_content_browser_assets` lists the cube under its destination path.
4. Create `M_PBR_Master` (see install step 5a) → `assign_material` on
   the cube with four placeholder textures. Confirm `MI_<name>` exists
   and is parented to the master.
5. `batch_place_actors` spawning three cubes from a manifest. Confirm a
   single ctrl-Z reverts all three — this is the single-undo guarantee.
6. Hand-rigged FBX through `wire_animation_blueprint` with
   `anim_blueprint_path="create_default"` → confirm the ABP exists next
   to the mesh.
7. Only after 1–6 pass: `/gen-asset "test prop"` end-to-end with
   TRELLIS + Blender MCP both running.

## Troubleshooting

| Symptom                                              | Likely cause                                      |
|------------------------------------------------------|---------------------------------------------------|
| `PythonScriptPlugin is not available`                | Plugin disabled in editor — check Edit > Plugins  |
| `Failed to connect to Unreal at 127.0.0.1:55557`     | Editor not running, or another UE editor on this port |
| `Failed to bind listener socket to 127.0.0.1:55557`  | Two editors fighting over the same port — set `UNREAL_MCP_PORT` differently for the second |
| `Python handler timed out`                           | Long FBX import — bump `UE_MCP_HANDLER_TIMEOUT_SEC` |
| `master material not found: /UnrealMCP/Materials/...`| Plugin's `Content/Materials/M_PBR_Master.uasset` missing — see VENDOR.md |
| `IK retargeting requires a manually-authored IKRetargeter` | Expected — auto-IK-rig generation is v2 work |

## Known limitations (v1)

- **Skeletal LODs not auto-generated** — only static. Skeletal
  auto-reduction needs per-asset bone-removal config.
- **IK retargeting is manual-rig-required.** The tool refuses to fake
  success on missing rigs.
- **Long-running imports block the editor UI** for the duration. Async
  progress is post-v1.
- **Game-thread serialization** — concurrent MCP calls queue, not
  parallelise. Documented behaviour.
- **Mixamo's API is reverse-engineered** and may break without notice.

## License

MIT — see `LICENSE` and `VENDOR.md`.
