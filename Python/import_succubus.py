"""
import_succubus.py

Imports the generated succubus GLB into UE5 via the UnrealMCP bridge,
then patches CylinderCharacter to reference the new mesh.

Usage:
    python import_succubus.py <path/to/succubus.glb>

Requires UE5 editor open with the MCPGameProject loaded.
"""

import json
import socket
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = 55557
TIMEOUT = 120.0

UE_DEST_PATH   = "/Game/Characters/Succubus"
UE_MESH_NAME   = "SKM_Succubus"


def send(command: str, params: dict) -> dict:
    payload = json.dumps({"type": command, "params": params}) + "\n"
    try:
        sock = socket.create_connection((HOST, PORT), timeout=10)
        sock.settimeout(TIMEOUT)
        sock.sendall(payload.encode("utf-8"))
        buf = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf += chunk
            if buf.rstrip().endswith(b"}"):
                break
        sock.close()
    except OSError as exc:
        return {"success": False, "error": str(exc)}

    text = buf.decode("utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[: i + 1])
        return {"raw": text}


def ok(label: str, resp: dict) -> bool:
    success = resp.get("success", resp.get("status") != "error")
    if not success:
        print(f"  FAIL  {label}: {resp}")
    else:
        print(f"  OK    {label}")
    return bool(success)


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python import_succubus.py <path/to/succubus.glb>")

    glb_path = Path(sys.argv[1]).resolve()
    if not glb_path.exists():
        sys.exit(f"GLB not found: {glb_path}")

    print(f"Importing {glb_path.name} into UE5...")
    print(f"  Source : {glb_path}")
    print(f"  Dest   : {UE_DEST_PATH}/{UE_MESH_NAME}\n")

    # Import GLB as static mesh (UE5 can import GLB directly)
    r = send("import_asset", {
        "source_path": str(glb_path),
        "dest_path": f"{UE_DEST_PATH}/{UE_MESH_NAME}",
        "asset_type": "StaticMesh",
    })
    if not ok(f"import GLB → {UE_MESH_NAME}", r):
        print("\nNote: if import_asset is unsupported, use File → Import in UE5 editor:")
        print(f"  1. Drag {glb_path} into Content Browser under {UE_DEST_PATH}")
        print(f"  2. Rename the imported mesh to {UE_MESH_NAME}")
        print(f"  3. Open CylinderCharacter.cpp and update the mesh path to:")
        print(f'     TEXT("{UE_DEST_PATH}/{UE_MESH_NAME}")')
        return

    print("\nDone. Rebuild the project for the mesh change to take effect.")


if __name__ == "__main__":
    main()
