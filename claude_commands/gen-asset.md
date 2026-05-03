---
description: Generate a 3D asset from a text prompt (TRELLIS → Blender MCP → Mixamo → UE5)
argument-hint: "<text prompt describing the asset>"
allowed-tools: Bash, Read, Write, Edit, mcp__unreal_mcp__*
---

# Generate asset from text

You are running the full asset pipeline on the Windows dev box. End-to-end:
TRELLIS generates a textured GLB → Blender cleans it up and exports FBX →
(if humanoid) Mixamo auto-rigs it → UE5 imports it via the UnrealMCP MCP
server → materials are assigned → optional AnimBP wiring → Telegram notify.

**Prompt:** $ARGUMENTS

**Required environment:**

| Var                       | Default                            | Purpose                       |
|---------------------------|------------------------------------|-------------------------------|
| `TRELLIS_ENDPOINT`        | `http://localhost:8188`            | TRELLIS HTTP API              |
| `BLENDER_MCP_ENDPOINT`    | `http://localhost:9876`            | Blender MCP server            |
| `STAGING_DIR`             | `D:/AssetPipeline/staging`         | TRELLIS GLB + textures land here |
| `EXPORT_DIR`              | `D:/AssetPipeline/export`          | Cleaned FBX lands here        |
| `STATE_DIR`               | `D:/AssetPipeline/state`           | Per-asset checkpoint files    |
| `MIXAMO_TOKEN_PATH`       | `~/.mixamo/token.json`             | Cached Adobe IMS token        |
| `TELEGRAM_BOT_TOKEN`      | (required)                         | Telegram credentials          |
| `TELEGRAM_CHAT_ID`        | (required)                         |                               |
| `UNREAL_CONTENT_ROOT`     | `/Game/SiblingGame`                | Content browser root for new assets |

**Before you start:** verify TRELLIS, Blender MCP, and the UE5 editor are
all running on this machine. The UE5 MCP server must be up — check that
the `import_fbx_asset` MCP tool is available.

## Steps

Use checkpoint state at `${STATE_DIR}/<asset_id>.json`. If the user passed
`--resume <asset_id>`, load that file and skip already-completed steps.

1. **Generate `asset_id`** = `slug(prompt) + '_' + timestamp` (slugify
   removes punctuation, lowercases, joins with underscores). Write the
   initial state file.

2. **TRELLIS generate.** POST to `${TRELLIS_ENDPOINT}/api/v1/generate` with
   `{"prompt": "<prompt>", "output_dir": "${STAGING_DIR}/${asset_id}"}`.
   Poll `/api/v1/jobs/<job_id>` every 5s until `status == "complete"`.
   Wrap with 3-retry exponential backoff (2s/4s/8s) on transient HTTP
   errors. Record `glb_path`, `albedo_path`, `normal_path`, `orm_path` in
   the checkpoint.

3. **Release VRAM** before invoking UE5 import (3090 can't host both at
   once). POST `${TRELLIS_ENDPOINT}/api/v1/unload`. If TRELLIS doesn't
   expose unload, document this — for now try the call and continue on
   404.

4. **Heuristic: humanoid?** Read the GLB header — if the bone count is in
   the 16–80 range AND the bounding box is taller than wide, treat as
   humanoid (`is_humanoid = True`). Otherwise non-humanoid (props, env).
   Stash in checkpoint.

5. **Blender cleanup.** POST to `${BLENDER_MCP_ENDPOINT}/run-script` with
   `{"script": "<contents of claude_commands/blender_scripts/cleanup.py>",
   "args": {"input_glb": "<glb_path>", "output_fbx":
   "${EXPORT_DIR}/${asset_id}.fbx", "is_humanoid": <bool>,
   "target_height_cm": 180}}`. Wait for completion. The script decimates
   to 32k tris, recenters, scales, triangulates, T-pose-aligns if
   humanoid, and FBX-exports with `embed_textures=False`.

6. **Mixamo auto-rig** (only if `is_humanoid`). Run
   `python claude_commands/mixamo_client.py rig
   --input ${EXPORT_DIR}/${asset_id}.fbx
   --output ${EXPORT_DIR}/${asset_id}_rigged.fbx
   --token ${MIXAMO_TOKEN_PATH}`. On success, set `rigged_fbx` in
   checkpoint. On Mixamo failure (auto-detect markers fail, non-humanoid
   classification, API error), log the reason, set `rigged = False`, and
   continue with the unrigged FBX as a static mesh.

7. **UE5 import.** Call MCP tool `import_fbx_asset`:
   - Rigged path: `file_path=<rigged_fbx>`,
     `destination_path=${UNREAL_CONTENT_ROOT}/Characters/<category>`,
     `asset_name=<id>`, `skeleton_path=""` (let UE create a fresh
     skeleton from the Mixamo bones), `build_nanite=False`.
   - Static path: `destination_path=${UNREAL_CONTENT_ROOT}/Props/<category>`,
     `build_nanite=False` (TRELLIS geometry is non-manifold-prone).
   Record returned `asset_path` in checkpoint.

8. **Materials.** Call `assign_material` with:
   ```
   asset_path=<imported asset_path>
   texture_paths={"Albedo": "<albedo>", "Normal": "<normal>"}
   orm_path=<orm_path>
   ```
   The handler creates `MI_<asset_name>` parented to the plugin's
   `M_PBR_Master` and wires the texture parameters.

9. **Animation BP wiring** (only if rigged). Call
   `wire_animation_blueprint(skeletal_mesh_path=<asset_path>,
   anim_blueprint_path="create_default", retarget_to_mannequin=False)`.
   Retargeting is left off by default since Mixamo skeletons need a
   manually-authored IK Retargeter (see decision #5 in the plan).

10. **Telegram notify.** POST to
    `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`
    with `chat_id=${TELEGRAM_CHAT_ID}` and a body summarising:
    - prompt
    - final asset_path in the content browser
    - whether rigged
    - any warnings from the pipeline (LOD failures, missing textures)

## Failure handling

After every step, write the updated checkpoint. On any step failure:

1. Print the resume command: `/gen-asset --resume <asset_id>`
2. Send a Telegram failure message with the failed step name and error.
3. Stop — do not attempt subsequent steps.

## Risk callouts (read these once)

- Mixamo's API is community-reverse-engineered. If `mixamo_client.py`
  starts failing with HTTP 4xx/5xx that look like API shape changes,
  open an issue — the upstream contract has shifted.
- Mixamo refuses non-humanoid uploads. The pipeline degrades gracefully
  to a StaticMesh in that case.
- First-ever run requires a one-time browser-based Adobe IMS login. The
  token cache at `${MIXAMO_TOKEN_PATH}` survives subsequent runs until
  refresh fails (~30 days typically).
- Both TRELLIS and UE5 want significant VRAM. Step 3 (TRELLIS unload) is
  not optional — skipping it OOMs on the 3090.
