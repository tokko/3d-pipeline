"""
Dispatch + result-file + try/except wrapper for editor-side handlers.

The C++ side calls dispatch_to_file(command, params_json, result_path).
We import the matching handler module, invoke its function with the
parsed params, and write the JSON result to result_path. Exceptions are
caught and serialised so the C++ side never blocks waiting for output.
"""

import importlib
import json
import traceback


# command name -> (module_under_unreal_mcp_pipeline, function_name)
_REGISTRY = {
    "import_fbx_asset":            ("asset_import",     "import_fbx_asset"),
    "get_content_browser_assets":  ("content_browser",  "get_content_browser_assets"),
    "assign_material":             ("material_assign",  "assign_material"),
    "wire_animation_blueprint":    ("animation_wire",   "wire_animation_blueprint"),
    "batch_place_actors":          ("scene_place",      "batch_place_actors"),
    "delete_asset":                ("stretch",          "delete_asset"),
    "rename_asset":                ("stretch",          "rename_asset"),
    "save_all_dirty":              ("stretch",          "save_all_dirty"),
    "compile_anim_blueprint":      ("stretch",          "compile_anim_blueprint"),
}


def dispatch_to_file(command, params_json, result_path):
    """Run a handler and persist its result. Never raises across the boundary."""
    try:
        if command not in _REGISTRY:
            result = {"success": False, "error": f"unknown command: {command}"}
        else:
            params = json.loads(params_json) if params_json else {}
            mod_name, fn_name = _REGISTRY[command]
            mod = importlib.import_module(f"unreal_mcp_pipeline.{mod_name}")
            # Reload during development so iterating on handlers doesn't
            # require restarting the editor.
            importlib.reload(mod)
            handler = getattr(mod, fn_name)
            result = handler(**params)
            if not isinstance(result, dict):
                result = {"success": False,
                          "error": f"handler {command} returned non-dict: {type(result).__name__}"}
    except Exception as exc:  # noqa: BLE001 — boundary catch is intentional
        result = {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
