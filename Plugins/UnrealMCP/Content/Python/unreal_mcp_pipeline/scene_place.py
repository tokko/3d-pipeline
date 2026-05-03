"""
batch_place_actors — spawn many actors from a JSON manifest.

Wrapped in a single editor undo transaction so ctrl-Z reverts the whole
batch.
"""

import json
import os

import unreal


def batch_place_actors(manifest_path, level_path="", save_level=True):
    if not os.path.isfile(manifest_path):
        return {"success": False, "error": f"manifest not found: {manifest_path}"}

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    actors = manifest.get("actors")
    if not isinstance(actors, list):
        return {"success": False, "error": "manifest missing 'actors' list"}

    if level_path:
        if not unreal.EditorLevelLibrary.load_level(level_path):
            return {"success": False, "error": f"failed to load level: {level_path}"}

    placed, failed = [], []
    with unreal.ScopedEditorTransaction("MCP: batch_place_actors"):
        for spec in actors:
            try:
                placed.append(_spawn_one(spec))
            except Exception as exc:  # noqa: BLE001
                failed.append({"spec": spec, "error": str(exc)})

    if save_level:
        unreal.EditorLevelLibrary.save_current_level()

    return {
        "success": not failed,
        "placed": placed,
        "failed": failed,
        "level_path": level_path or unreal.EditorLevelLibrary.get_editor_world().get_path_name(),
    }


def _spawn_one(spec):
    asset_path = spec.get("asset_path")
    if not asset_path:
        raise ValueError("missing asset_path")

    asset = unreal.load_asset(asset_path)
    if asset is None:
        raise ValueError(f"asset not found: {asset_path}")

    location = unreal.Vector(*spec.get("location", [0.0, 0.0, 0.0]))
    rotation = unreal.Rotator(*spec.get("rotation", [0.0, 0.0, 0.0]))

    actor = unreal.EditorLevelLibrary.spawn_actor_from_object(asset, location, rotation)
    if actor is None:
        raise RuntimeError(f"spawn_actor_from_object returned None for {asset_path}")

    label = spec.get("name") or asset.get_name()
    actor.set_actor_label(label)

    scale = spec.get("scale", [1.0, 1.0, 1.0])
    actor.set_actor_scale3d(unreal.Vector(*scale))

    for tag in spec.get("tags", []):
        actor.tags.append(tag)

    return {"name": actor.get_actor_label(), "asset_path": asset_path}
