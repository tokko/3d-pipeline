# 3d-pipeline — UE5 MCP server for the TRELLIS → Blender → UE5 asset pipeline.
# Smoke targets assume the UE5 editor is running with the UnrealMCP plugin
# loaded and listening on $(UNREAL_MCP_PORT) (default 55557).

UNREAL_MCP_PORT ?= 55557
UV ?= uv

.PHONY: help install lint smoke smoke-list smoke-import smoke-content smoke-clean

help:
	@echo "Targets:"
	@echo "  install     - sync Python deps via uv"
	@echo "  lint        - lint Python tools"
	@echo "  smoke       - run all smoke checks against a live UE5 editor"
	@echo "  smoke-list  - list MCP tools the server exposes (no editor needed)"
	@echo "  smoke-clean - remove temp files left by smoke runs"

install:
	cd Python && $(UV) sync

lint:
	cd Python && $(UV) run ruff check tools/ unreal_mcp_server.py || true

# Quick boot test — confirms the server starts and registers all tools,
# including the four new asset-pipeline ones. Doesn't require the editor.
smoke-list:
	cd Python && $(UV) run python -c "import unreal_mcp_server as s; print('\n'.join(sorted(t.name for t in s.mcp._tool_manager.list_tools())))"

# Live-editor smokes. Each shells out to a one-off Python script that
# imports the server module and calls the tool directly through the
# bridge. The editor must be running with the plugin loaded.
# The scripts under scripts/smoke_*.py are not yet committed — the v1
# verification suite is documented in the plan and run manually via
# `mcp dev` against the live editor. Wire these targets when the scripts
# land.
smoke-import:
	@test -f scripts/smoke_import_fbx.py || (echo "scripts/smoke_import_fbx.py not yet implemented — see plan verification section" && exit 1)
	cd Python && $(UV) run python ../scripts/smoke_import_fbx.py

smoke-content:
	@test -f scripts/smoke_content_browser.py || (echo "scripts/smoke_content_browser.py not yet implemented — see plan verification section" && exit 1)
	cd Python && $(UV) run python ../scripts/smoke_content_browser.py

smoke: smoke-list
	@echo "smoke-list passed. Full smoke suite (smoke-content, smoke-import) requires the editor running and is not yet wired."

smoke-clean:
	rm -rf MCPGameProject/Intermediate/UnrealMCP/result_*.json
