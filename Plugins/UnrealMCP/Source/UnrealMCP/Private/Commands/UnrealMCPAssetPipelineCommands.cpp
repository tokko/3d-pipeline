#include "Commands/UnrealMCPAssetPipelineCommands.h"
#include "Commands/UnrealMCPCommonUtils.h"
#include "IPythonScriptPlugin.h"
#include "PythonScriptTypes.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/DateTime.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformMisc.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
    // Commands this handler owns. Kept in one place so HandleCommand and
    // OwnsCommand can't drift.
    const TArray<FString>& GetOwnedCommands()
    {
        static const TArray<FString> Owned = {
            TEXT("import_fbx_asset"),
            TEXT("assign_material"),
            TEXT("wire_animation_blueprint"),
            TEXT("batch_place_actors"),
            TEXT("get_content_browser_assets"),
            // stretch
            TEXT("delete_asset"),
            TEXT("rename_asset"),
            TEXT("save_all_dirty"),
            TEXT("compile_anim_blueprint")
        };
        return Owned;
    }

    // Forward-slash path safe for embedding in Python source on Windows.
    FString NormalizePath(const FString& InPath)
    {
        FString Full = FPaths::ConvertRelativePathToFull(InPath);
        Full.ReplaceInline(TEXT("\\"), TEXT("/"));
        return Full;
    }

    // Render a JSON object to a compact string suitable for Python json.loads.
    FString JsonObjectToCompactString(const TSharedPtr<FJsonObject>& Obj)
    {
        FString Out;
        TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
            TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
        if (Obj.IsValid())
        {
            FJsonSerializer::Serialize(Obj.ToSharedRef(), Writer);
        }
        else
        {
            Out = TEXT("{}");
        }
        return Out;
    }
}

FUnrealMCPAssetPipelineCommands::FUnrealMCPAssetPipelineCommands()
{
}

bool FUnrealMCPAssetPipelineCommands::OwnsCommand(const FString& CommandType)
{
    return GetOwnedCommands().Contains(CommandType);
}

double FUnrealMCPAssetPipelineCommands::GetHandlerTimeoutSeconds() const
{
    FString FromEnv = FPlatformMisc::GetEnvironmentVariable(TEXT("UE_MCP_HANDLER_TIMEOUT_SEC"));
    if (!FromEnv.IsEmpty())
    {
        const double Parsed = FCString::Atod(*FromEnv);
        if (Parsed > 0.0)
        {
            return Parsed;
        }
    }
    return 300.0;
}

TSharedPtr<FJsonObject> FUnrealMCPAssetPipelineCommands::HandleCommand(const FString& CommandType, const TSharedPtr<FJsonObject>& Params)
{
    if (!OwnsCommand(CommandType))
    {
        return FUnrealMCPCommonUtils::CreateErrorResponse(
            FString::Printf(TEXT("Unknown asset-pipeline command: %s"), *CommandType));
    }

    IPythonScriptPlugin* PyPlugin = IPythonScriptPlugin::Get();
    if (!PyPlugin || !PyPlugin->IsPythonAvailable())
    {
        return FUnrealMCPCommonUtils::CreateErrorResponse(
            TEXT("PythonScriptPlugin is not available — enable it in your project's plugin settings."));
    }

    // Build a unique temp file path for the Python handler to write into.
    const FString TempDir = FPaths::ProjectIntermediateDir() / TEXT("UnrealMCP");
    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
    PlatformFile.CreateDirectoryTree(*TempDir);
    const FString ResultPath = NormalizePath(TempDir /
        FString::Printf(TEXT("result_%s_%s.json"),
            *CommandType,
            *FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphens)));

    // Best-effort: ensure no stale file from a previous aborted call.
    if (PlatformFile.FileExists(*ResultPath))
    {
        PlatformFile.DeleteFile(*ResultPath);
    }

    const FString ParamsJson = JsonObjectToCompactString(Params);

    // Triple-quoted raw-style string so braces and quotes inside the JSON
    // body don't clash with Python source. Escape the closing triple-quote
    // sequence defensively (it can't appear in well-formed JSON, but being
    // explicit is cheap).
    FString SafeParams = ParamsJson;
    SafeParams.ReplaceInline(TEXT("\"\"\""), TEXT("\\\"\\\"\\\""));

    const FString PyCommand = FString::Printf(
        TEXT("import sys, importlib\n")
        TEXT("import unreal_mcp_pipeline\n")
        TEXT("importlib.reload(unreal_mcp_pipeline)\n")
        TEXT("unreal_mcp_pipeline.dispatch_to_file(r'%s', r'''%s''', r'%s')\n"),
        *CommandType, *SafeParams, *ResultPath);

    FPythonCommandEx PyCmd;
    PyCmd.ExecutionMode = EPythonCommandExecutionMode::ExecuteStatement;
    PyCmd.Command = PyCommand;
    PyCmd.Flags = EPythonCommandFlags::None;

    const bool bExecOk = PyPlugin->ExecPythonCommandEx(PyCmd);
    if (!bExecOk)
    {
        FString ErrMsg = PyCmd.CommandResult;
        if (ErrMsg.IsEmpty())
        {
            ErrMsg = TEXT("Python execution failed (no error string returned).");
        }
        return FUnrealMCPCommonUtils::CreateErrorResponse(
            FString::Printf(TEXT("Python handler exec failed: %s"), *ErrMsg));
    }

    // Wait for the result file. ExecPythonCommandEx is synchronous on the
    // game thread, so the file should already exist; the loop is defensive
    // against handlers that schedule deferred I/O.
    const double Deadline = FPlatformTime::Seconds() + GetHandlerTimeoutSeconds();
    while (!PlatformFile.FileExists(*ResultPath))
    {
        if (FPlatformTime::Seconds() > Deadline)
        {
            return FUnrealMCPCommonUtils::CreateErrorResponse(
                FString::Printf(TEXT("Python handler '%s' timed out producing result file at %s"),
                    *CommandType, *ResultPath));
        }
        FPlatformProcess::Sleep(0.05f);
    }

    FString ResultJsonStr;
    if (!FFileHelper::LoadFileToString(ResultJsonStr, *ResultPath))
    {
        return FUnrealMCPCommonUtils::CreateErrorResponse(
            FString::Printf(TEXT("Python handler wrote result file but it could not be read: %s"), *ResultPath));
    }
    PlatformFile.DeleteFile(*ResultPath);

    TSharedPtr<FJsonObject> ResultObj;
    TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(ResultJsonStr);
    if (!FJsonSerializer::Deserialize(Reader, ResultObj) || !ResultObj.IsValid())
    {
        return FUnrealMCPCommonUtils::CreateErrorResponse(
            FString::Printf(TEXT("Python handler returned malformed JSON: %s"),
                *ResultJsonStr.Left(512)));
    }
    return ResultObj;
}
