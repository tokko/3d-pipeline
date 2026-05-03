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

## Slash commands

```bash
# install — copy or symlink into Claude Code's commands dir
cp claude_commands/*.md ~/.claude/commands/
```

The commands depend on:
- `claude_commands/mixamo_client.py` — Mixamo HTTP client (community
  reverse-engineered API; expect occasional breakage). First run requires
  a one-time browser-based Adobe IMS login; token cached at
  `~/.mixamo/token.json`.
- `claude_commands/blender_scripts/cleanup.py` — invoked by Blender MCP
  to decimate, recenter, scale, and FBX-export TRELLIS GLB output.

## Verification

```bash
make smoke-list          # sanity check — server registers all tools (no editor needed)
make smoke               # full run — needs editor open with plugin loaded
```

Manual end-to-end smokes (see plan `verification` section for the full
checklist):

1. `import_fbx_asset` of a hand-exported cube → confirm in content browser
2. `get_content_browser_assets` lists it
3. `assign_material` (texture mode) wires four placeholder textures
4. `batch_place_actors` spawns three actors with ctrl-Z reverting all
5. `wire_animation_blueprint` against a rigged mesh → ABP exists
6. `/gen-asset "test prompt"` end-to-end on Windows with TRELLIS + Blender MCP

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
