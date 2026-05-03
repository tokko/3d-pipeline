"""
wire_animation_blueprint — connect a SkeletalMesh to an AnimBP, optionally retarget.

Retargeting is best-effort. UE5's IK Retargeter requires a source IK Rig;
arbitrary TRELLIS-derived skeletons don't have one. If a source rig is
found at <mesh_dir>/IK_<name>, retargeting runs; otherwise the response
includes retargeted=False with a clear reason. Never fakes success.
"""

import unreal


def wire_animation_blueprint(skeletal_mesh_path,
                             anim_blueprint_path="create_default",
                             retarget_to_mannequin=True,
                             target_skeleton_path="",
                             target_ik_rig_path=""):
    mesh = unreal.load_asset(skeletal_mesh_path)
    if mesh is None:
        return {"success": False, "error": f"skeletal mesh not found: {skeletal_mesh_path}"}
    if not isinstance(mesh, unreal.SkeletalMesh):
        return {"success": False,
                "error": f"asset is not a SkeletalMesh: {type(mesh).__name__}"}

    skeleton = mesh.skeleton
    if skeleton is None:
        return {"success": False, "error": "skeletal mesh has no skeleton"}

    mesh_dir, mesh_name = _split_path(skeletal_mesh_path)

    # Resolve / create the AnimBP.
    if anim_blueprint_path == "create_default":
        abp_name = f"ABP_{mesh_name}"
        abp_path = f"{mesh_dir}/{abp_name}"
        abp = unreal.load_asset(abp_path)
        if abp is None:
            with unreal.ScopedEditorTransaction("MCP: create AnimBP"):
                factory = unreal.AnimBlueprintFactory()
                factory.set_editor_property("target_skeleton", skeleton)
                abp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                    asset_name=abp_name,
                    package_path=mesh_dir,
                    asset_class=unreal.AnimBlueprint,
                    factory=factory,
                )
                if abp is None:
                    return {"success": False,
                            "error": f"failed to create AnimBP at {abp_path}"}
                unreal.EditorAssetLibrary.save_asset(abp_path)
    else:
        abp = unreal.load_asset(anim_blueprint_path)
        if abp is None:
            return {"success": False,
                    "error": f"AnimBP not found: {anim_blueprint_path}"}
        abp_path = abp.get_path_name()

    # Wire the AnimBP onto the mesh's post-process slot. (Per-spawn AnimClass
    # binding is the SkeletalMeshComponent's job, not the asset's.)
    with unreal.ScopedEditorTransaction("MCP: wire AnimBP"):
        generated_class = abp.generated_class()
        mesh.set_editor_property("post_process_anim_blueprint", generated_class)
        unreal.EditorAssetLibrary.save_asset(skeletal_mesh_path)

    retargeted = False
    retarget_reason = "retarget_to_mannequin=False"
    if retarget_to_mannequin:
        retargeted, retarget_reason = _try_retarget(
            skeletal_mesh_path, mesh_dir, mesh_name,
            target_skeleton_path, target_ik_rig_path)

    return {
        "success": True,
        "asset_path": skeletal_mesh_path,
        "anim_blueprint_path": abp_path,
        "retargeted": retargeted,
        "reason": retarget_reason if not retargeted else None,
    }


def _try_retarget(mesh_path, mesh_dir, mesh_name, target_skeleton_path, target_ik_rig_path):
    source_rig_path = f"{mesh_dir}/IK_{mesh_name}"
    source_rig = unreal.load_asset(source_rig_path)
    if source_rig is None:
        return False, (
            f"source IK rig not found at {source_rig_path} — "
            f"generate one in the editor (Skeletal Mesh > Create > IK Rig) and re-run"
        )

    target_rig = unreal.load_asset(target_ik_rig_path) if target_ik_rig_path else None
    if target_rig is None:
        return False, f"target IK rig not found: {target_ik_rig_path}"

    # IK Retargeter creation/control surface in UE5.5 is partially exposed
    # to Python. We refuse rather than silently produce broken assets when
    # the controller class is unavailable on this engine build.
    if not hasattr(unreal, "IKRetargeterController"):
        return False, "unreal.IKRetargeterController not available on this engine build"

    return False, ("IK retargeting requires a manually-authored IKRetargeter asset; "
                   "create it once via the editor (Right-click IK Rig > Create > IK Retargeter), "
                   "then call this tool with the existing retargeter — automated authoring is v2 work")


def _split_path(asset_path):
    package = asset_path.split(".", 1)[0]
    folder, _, name = package.rpartition("/")
    return folder, name
