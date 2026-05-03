"""
assign_material — material assignment + MI upsert (editor-side).

Two modes:
  - material_path:   assign an existing material to the mesh slot.
  - texture_paths:   create or upsert a MaterialInstanceConstant parented
                     to master_material_path, set Albedo/Normal/Roughness/
                     Metallic (or ORM) parameters, then assign.

The MI is stored next to the target mesh as MI_<mesh-name>. Re-running with
the same target overwrites the existing MI's parameters in place.
"""

import os

import unreal


def assign_material(asset_path, material_path="", texture_paths=None,
                    orm_path="", master_material_path="/UnrealMCP/Materials/M_PBR_Master",
                    slot_index=0, replace_existing=True):
    if not asset_path:
        return {"success": False, "error": "asset_path is required"}

    mesh = unreal.load_asset(asset_path)
    if mesh is None:
        return {"success": False, "error": f"mesh asset not found: {asset_path}"}

    texture_paths = dict(texture_paths or {})

    with unreal.ScopedEditorTransaction("MCP: assign_material"):
        if material_path:
            material = unreal.load_asset(material_path)
            if material is None:
                return {"success": False, "error": f"material not found: {material_path}"}
            assigned_path = material.get_path_name()
        else:
            if not texture_paths and not orm_path:
                return {"success": False, "error": "provide either material_path, texture_paths, or orm_path"}

            master = unreal.load_asset(master_material_path)
            if master is None:
                return {"success": False,
                        "error": f"master material not found: {master_material_path} — "
                                 f"is the UnrealMCP plugin Content directory mounted?"}

            mesh_dir, mesh_name = _split_path(asset_path)
            mi_name = f"MI_{mesh_name}"
            mi_full = f"{mesh_dir}/{mi_name}"

            mi = unreal.load_asset(mi_full)
            if mi is not None and not replace_existing:
                return {"success": False, "error": f"material instance already exists: {mi_full}"}

            if mi is None:
                factory = unreal.MaterialInstanceConstantFactoryNew()
                mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                    asset_name=mi_name,
                    package_path=mesh_dir,
                    asset_class=unreal.MaterialInstanceConstant,
                    factory=factory,
                )
                if mi is None:
                    return {"success": False, "error": f"failed to create material instance at {mi_full}"}

            mi.set_editor_property("parent", master)

            unset = []
            for param_name, tex_path in texture_paths.items():
                tex = unreal.load_asset(tex_path) if tex_path else None
                if tex is None:
                    unset.append({"param": param_name, "texture_path": tex_path})
                    continue
                unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
                    mi, param_name, tex)

            if orm_path:
                orm_tex = unreal.load_asset(orm_path)
                if orm_tex is None:
                    unset.append({"param": "ORM", "texture_path": orm_path})
                else:
                    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
                        mi, "ORM", orm_tex)
                    # Master-material static switch: enable ORM packed mode.
                    unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                        mi, "UseORM", True)

            unreal.MaterialEditingLibrary.update_material_instance(mi)
            material = mi
            assigned_path = mi.get_path_name()
            unreal.EditorAssetLibrary.save_asset(assigned_path)

        _assign_to_slot(mesh, material, slot_index)
        unreal.EditorAssetLibrary.save_asset(asset_path)

    return {
        "success": True,
        "asset_path": asset_path,
        "material_path": assigned_path,
        "slot_index": slot_index,
        "missing_textures": unset if (not material_path) else [],
    }


def _split_path(asset_path):
    """Split /Game/Foo/Bar.Bar into (/Game/Foo, Bar)."""
    package = asset_path.split(".", 1)[0]
    folder, _, name = package.rpartition("/")
    return folder, name


def _assign_to_slot(mesh, material, slot_index):
    if isinstance(mesh, unreal.StaticMesh):
        mesh.set_material(slot_index, material)
        return
    if isinstance(mesh, unreal.SkeletalMesh):
        materials = list(mesh.materials)
        if slot_index >= len(materials):
            raise IndexError(f"slot_index {slot_index} out of range "
                             f"for skeletal mesh with {len(materials)} slots")
        materials[slot_index].material_interface = material
        mesh.materials = materials
        return
    raise TypeError(f"unsupported mesh type: {type(mesh).__name__}")
