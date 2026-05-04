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


def _ensure_skeletal_mesh_usage(material):
    """
    Walk to the parent UMaterial and enable bUsedWithSkeletalMesh if not set.
    Without this flag UE5 silently substitutes the default material at runtime.
    """
    parent = material
    while isinstance(parent, unreal.MaterialInstanceConstant):
        parent = parent.get_editor_property("parent")

    if not isinstance(parent, unreal.Material):
        return
    if parent.get_editor_property("used_with_skeletal_mesh"):
        return  # already set — nothing to do

    parent.set_editor_property("used_with_skeletal_mesh", True)
    unreal.MaterialEditingLibrary.recompile_material(parent)
    unreal.EditorAssetLibrary.save_asset(parent.get_path_name())


def _ensure_pbr_master(master_path):
    """
    Create /UnrealMCP/Materials/M_PBR_Master with TextureSampleParameter2D
    nodes for Albedo, Metallic, Roughness if it doesn't already exist.
    Always ensures bUsedWithSkeletalMesh=True regardless of whether the
    material was freshly created or already existed.
    Returns the material object (existing or newly created).
    """
    existing = unreal.load_asset(master_path)
    if existing is not None:
        _ensure_skeletal_mesh_usage(existing)
        return existing

    folder, name = master_path.rsplit("/", 1)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        asset_name=name,
        package_path=folder,
        asset_class=unreal.Material,
        factory=unreal.MaterialFactoryNew(),
    )
    if mat is None:
        raise RuntimeError(f"Failed to create master material at {master_path}")

    mel = unreal.MaterialEditingLibrary

    # Albedo parameter -> BaseColor
    n_alb = mel.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameter2D, -600, 300)
    n_alb.set_editor_property("parameter_name", "Albedo")

    # Metallic parameter -> Metallic
    n_met = mel.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameter2D, -600, 100)
    n_met.set_editor_property("parameter_name", "Metallic")
    n_met.set_editor_property("sampler_type",
                               unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)

    # Roughness parameter -> Roughness
    n_rgh = mel.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameter2D, -600, -100)
    n_rgh.set_editor_property("parameter_name", "Roughness")
    n_rgh.set_editor_property("sampler_type",
                               unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)

    mel.connect_material_property(n_alb, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(n_met, "R",   unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(n_rgh, "R",   unreal.MaterialProperty.MP_ROUGHNESS)

    mat.set_editor_property("used_with_skeletal_mesh", True)
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(master_path)
    return mat


def _create_direct_material(mat_path, texture_paths_dict):
    """
    Create a plain UMaterial (no MI chain) at mat_path with TextureSample
    nodes directly wired to BaseColor / Metallic / Roughness outputs.
    Sets bUsedWithSkeletalMesh=True.

    If the material already exists it is deleted and recreated from scratch so
    stale nodes from previous runs don't accumulate and shadow the connections.
    """
    mel = unreal.MaterialEditingLibrary
    folder, name = mat_path.rsplit("/", 1)

    mat = unreal.load_asset(mat_path)
    if mat is None:
        mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name=name,
            package_path=folder,
            asset_class=unreal.Material,
            factory=unreal.MaterialFactoryNew(),
        )
        if mat is None:
            raise RuntimeError(f"Failed to create material at {mat_path}")
    # Note: do NOT call delete_all_material_expressions — it crashes (IsRooted assert).
    # New nodes are added each call; connect_material_property replaces the connection
    # on each property pin, so the last-added node always wins.

    mat.set_editor_property("used_with_skeletal_mesh", True)

    # "" = first / default output (RGBA) of MaterialExpressionTextureSample.
    # "R" = red channel only (used for linear single-channel maps).
    channel_map = {
        "Albedo":    (unreal.MaterialProperty.MP_BASE_COLOR, "",  False),
        "Metallic":  (unreal.MaterialProperty.MP_METALLIC,   "R", True),
        "Roughness": (unreal.MaterialProperty.MP_ROUGHNESS,  "R", True),
    }
    y_pos = 200
    for param_name, tex_path in (texture_paths_dict or {}).items():
        if param_name not in channel_map:
            continue
        mp, pin, is_linear = channel_map[param_name]
        tex = unreal.load_asset(tex_path) if tex_path else None
        if tex is None:
            continue
        node = mel.create_material_expression(
            mat, unreal.MaterialExpressionTextureSample, -600, y_pos)
        node.set_editor_property("texture", tex)
        if is_linear:
            node.set_editor_property(
                "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        mel.connect_material_property(node, pin, mp)
        y_pos -= 200

    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(mat_path)
    return mat


def assign_material(asset_path, material_path="", texture_paths=None,
                    orm_path="", master_material_path="/UnrealMCP/Materials/M_PBR_Master",
                    slot_index=0, replace_existing=True, use_direct=False,
                    reparent_mi_to=""):
    if not asset_path:
        return {"success": False, "error": "asset_path is required"}

    mesh = unreal.load_asset(asset_path)
    if mesh is None:
        return {"success": False, "error": f"mesh asset not found: {asset_path}"}

    texture_paths = dict(texture_paths or {})

    with unreal.ScopedEditorTransaction("MCP: assign_material"):
        if reparent_mi_to:
            # Change an existing MI's parent to a different UMaterial/MI.
            # This lets us fix a broken MI parent without rebuilding the MI from scratch.
            mi = unreal.load_asset(material_path)
            if mi is None:
                return {"success": False, "error": f"MI not found: {material_path}"}
            new_parent = unreal.load_asset(reparent_mi_to)
            if new_parent is None:
                return {"success": False, "error": f"new parent not found: {reparent_mi_to}"}
            mi.set_editor_property("parent", new_parent)
            unreal.MaterialEditingLibrary.update_material_instance(mi)
            unreal.EditorAssetLibrary.save_asset(material_path)
            material = mi
            assigned_path = mi.get_path_name()
        elif material_path:
            material = unreal.load_asset(material_path)
            if material is None:
                return {"success": False, "error": f"material not found: {material_path}"}
            # Skeletal meshes require bUsedWithSkeletalMesh on the parent UMaterial.
            # Fix it here so callers don't have to know about this UE5 quirk.
            if isinstance(mesh, unreal.SkeletalMesh):
                _ensure_skeletal_mesh_usage(material)
            assigned_path = material.get_path_name()
        elif use_direct:
            # Create a plain UMaterial (no MI chain) so we skip the
            # M_PBR_Master parameter route entirely.
            if not texture_paths:
                return {"success": False,
                        "error": "use_direct requires texture_paths"}
            mesh_dir, mesh_name = _split_path(asset_path)
            direct_path = f"{mesh_dir}/M_{mesh_name}_Direct"
            material = _create_direct_material(direct_path, texture_paths)
            assigned_path = direct_path
        else:
            if not texture_paths and not orm_path:
                return {"success": False, "error": "provide either material_path, texture_paths, or orm_path"}

            master = _ensure_pbr_master(master_material_path)
            if master is None:
                return {"success": False,
                        "error": f"master material could not be created: {master_material_path}"}

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
        "missing_textures": unset if (not material_path and not use_direct) else [],
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
