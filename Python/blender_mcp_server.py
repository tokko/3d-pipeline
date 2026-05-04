"""
Blender MCP HTTP server — listens on :9876 (BLENDER_MCP_PORT).

POST /run-script  {"script": "<python source>", "args": {key: value, ...}}
  Writes the script to a temp file, runs Blender headlessly, returns stdout/stderr.

Args dict is converted to CLI flags:
  bool True  → --flag
  bool False → (omitted)
  other      → --key value

Run:
    uv run python blender_mcp_server.py
or:
    python blender_mcp_server.py
"""
import os
import subprocess
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

BLENDER_EXE = os.environ.get(
    "BLENDER_EXE",
    r"C:\blender\blender-4.2.16-windows-x64\blender.exe",
)
PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))
TIMEOUT = int(os.environ.get("BLENDER_MCP_TIMEOUT_SEC", "300"))

app = FastAPI(title="Blender MCP HTTP server", version="1.0.0")


class RunScriptRequest(BaseModel):
    script: str
    args: dict = {}


def _args_to_cli(args: dict) -> list[str]:
    """Convert {'key': value} → ['--key', 'value'] or ['--flag'] for booleans."""
    cli = []
    for key, value in args.items():
        if isinstance(value, bool):
            if value:
                cli.append(f"--{key}")
        elif value is not None:
            cli.extend([f"--{key}", str(value)])
    return cli


@app.get("/health")
def health():
    return {"status": "ok", "blender": BLENDER_EXE}


@app.post("/run-script")
def run_script(req: RunScriptRequest):
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(req.script)
        script_path = f.name

    try:
        cmd = [BLENDER_EXE, "--background", "--python", script_path, "--"] + _args_to_cli(req.args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)

        tail = lambda s: s[-3000:] if len(s) > 3000 else s  # noqa: E731

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Blender exited non-zero",
                    "returncode": result.returncode,
                    "stdout": tail(result.stdout),
                    "stderr": tail(result.stderr),
                },
            )

        return {
            "status": "ok",
            "returncode": result.returncode,
            "stdout": tail(result.stdout),
            "stderr": tail(result.stderr),
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail={"error": f"Blender timed out after {TIMEOUT}s"})
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


if __name__ == "__main__":
    if not Path(BLENDER_EXE).exists():
        print(f"WARNING: Blender not found at {BLENDER_EXE!r}. Set BLENDER_EXE env var.")
    print(f"Starting Blender MCP server on 127.0.0.1:{PORT} (blender={BLENDER_EXE})")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
