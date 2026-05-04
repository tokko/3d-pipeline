"""
Import the HY3D-baked PBR textures and wire them into M_Succubus_Base.
Run via:
  UnrealEditor.exe MCPGameProject.uproject -run=pythonscript -script=apply_succubus_textures.py -stdout -AllowStdOutLogVerbosity
"""
import unreal

CONTENT_DIR  = "/Game/Characters/Succubus"
ALBEDO_SRC   = r"D:\claude projects\unreal-game-poc\3d-pipeline\output\succubus\succubus_textured_final_tmp.jpg"
METALLIC_SRC = r"D:\claude projects\unreal-game-poc\3d-pipeline\output\succubus\succubus_textured_final_tmp_metallic.jpg"
ROUGH_SRC    = r"D:\claude projects\unreal-game-poc\3d-pipeline\output\succubus\succubus_textured_final_tmp_roughness.jpg"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

def import_tex(src, name, is_linear=False):
    task = unreal.AssetImportTask()
    task.filename = src
    task.destination_path = CONTENT_DIR
    task.destination_name = name
    task.replace_existing = True
    task.automated = True
    task.save = True
    asset_tools.import_asset_tasks([task])
    tex = unreal.load_asset(f"{CONTENT_DIR}/{name}")
    if tex is None:
        raise RuntimeError(f"Failed to import {src}")
    if is_linear:
        tex.set_editor_property("srgb", False)
        unreal.EditorAssetLibrary.save_asset(f"{CONTENT_DIR}/{name}")
    print(f"  Imported: {name}")
    return tex

print("=== Importing textures ===")
albedo_tex   = import_tex(ALBEDO_SRC,   "T_Succubus_Albedo",    is_linear=False)
metallic_tex = import_tex(METALLIC_SRC, "T_Succubus_Metallic",  is_linear=True)
rough_tex    = import_tex(ROUGH_SRC,    "T_Succubus_Roughness", is_linear=True)

print("=== Rebuilding material graph ===")
mat = unreal.load_asset("/Game/Characters/Succubus/M_Succubus_Base")
if mat is None:
    raise RuntimeError("Could not load M_Succubus_Base")

mel = unreal.MaterialEditingLibrary

# Wipe existing expressions so we start clean
mel.delete_all_material_expressions(mat)

# --- Albedo node ---
alb_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -500, 200)
alb_node.set_editor_property("texture", albedo_tex)

# --- Metallic node ---
met_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -500, 0)
met_node.set_editor_property("texture", metallic_tex)
met_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)

# --- Roughness node ---
rgh_node = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -500, -200)
rgh_node.set_editor_property("texture", rough_tex)
rgh_node.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)

# --- Wire to material outputs ---
mel.connect_material_property(alb_node, "RGB",  unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(met_node, "R",    unreal.MaterialProperty.MP_METALLIC)
mel.connect_material_property(rgh_node, "R",    unreal.MaterialProperty.MP_ROUGHNESS)

# Compile
mel.recompile_material(mat)
unreal.EditorAssetLibrary.save_asset("/Game/Characters/Succubus/M_Succubus_Base")

print("=== Done — M_Succubus_Base now has PBR textures ===")
