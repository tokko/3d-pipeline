"""
setup_cylinder_game.py

Creates the minimal cylinder game level via the UnrealMCP TCP bridge.
Requires the UE5 editor to be running with the MCPGameProject loaded
and the UnrealMCP plugin listening on port 55557.

Run after the C++ build so CylinderCharacter / CylinderGameMode are loaded.
"""

import json
import socket
import sys
import time

HOST = "127.0.0.1"
PORT = 55557
TIMEOUT = 90.0


def send(command: str, params: dict) -> dict:
    """Open a fresh TCP connection for each command (matches server's one-cmd-per-conn behaviour)."""
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
            # Stop when we have a complete JSON object (response ends with } or \n)
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
            if ch == "{":
                depth += 1
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


def ok_or_exists(label: str, resp: dict) -> bool:
    """Treats 'already exists' errors as success (idempotent spawns)."""
    err = resp.get("error", "")
    if "already exists" in err:
        print(f"  OK    {label} (already exists)")
        return True
    return ok(label, resp)


def probe() -> bool:
    """Quick check that the MCP bridge is reachable."""
    try:
        s = socket.create_connection((HOST, PORT), timeout=5)
        s.close()
        return True
    except OSError:
        return False


def main():
    print(f"Checking UE5 MCP bridge on {HOST}:{PORT}...")
    if not probe():
        sys.exit("Cannot connect. Make sure the editor is running with the UnrealMCP plugin active.")
    print("Bridge reachable. Sending commands...\n")

    # ── Input mappings (legacy) ──────────────────────────────────────────────
    print("= Input mappings =")
    axis_maps = [
        ("MoveForward", "W",        "Axis", 1.0),
        ("MoveForward", "S",        "Axis", -1.0),
        ("MoveRight",   "D",        "Axis", 1.0),
        ("MoveRight",   "A",        "Axis", -1.0),
        ("Turn",        "R",        "Axis", 1.0),
        ("Turn",        "Q",        "Axis", -1.0),
    ]
    for action, key, itype, scale in axis_maps:
        r = send("create_input_mapping",
                 {"action_name": action, "key": key, "input_type": itype})
        ok(f"{action} <- {key} ({scale:+.0f})", r)

    r = send("create_input_mapping",
             {"action_name": "Jump", "key": "SpaceBar", "input_type": "Action"})
    ok("Jump <- SpaceBar", r)

    # ── Floor (StaticMeshActor — avoids Blueprint compile hang) ──────────────
    print("\n= Floor plane =")
    # Delete stale actor from a previous run if present
    send("delete_actor", {"name": "FloorActor"})

    r = send("spawn_actor", {
        "name": "FloorActor",
        "type": "StaticMeshActor",
        "location": [0.0, 0.0, -1.0],
        "rotation": [0.0, 0.0, 0.0],
    })
    ok("spawn FloorActor (StaticMeshActor)", r)

    # Plane BasicShape is 100x100 UU; path needs double-suffix for asset loader
    r = send("set_actor_static_mesh", {
        "name": "FloorActor",
        "mesh": "/Engine/BasicShapes/Plane.Plane",
    })
    ok("set Plane mesh on FloorActor", r)

    # Scale 50x -> 5000x5000 UU floor
    r = send("set_actor_transform", {
        "name": "FloorActor",
        "scale": [50.0, 50.0, 1.0],
    })
    ok("scale floor 50x50", r)

    # ── Sky / Atmosphere ─────────────────────────────────────────────────────
    print("\n= Sky atmosphere + lighting =")
    r = send("spawn_actor", {
        "name": "SkyAtmo",
        "type": "SkyAtmosphere",
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
    })
    ok_or_exists("spawn SkyAtmosphere", r)

    r = send("spawn_actor", {
        "name": "SkyLightActor",
        "type": "SkyLight",
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
    })
    ok_or_exists("spawn SkyLight", r)

    # Golden hour: sun 20 degrees above horizon (pitch -20), southeast (yaw 45)
    r = send("spawn_actor", {
        "name": "SunLight",
        "type": "DIRECTIONALLIGHT",
        "location": [0.0, 0.0, 0.0],
        "rotation": [-20.0, 45.0, 0.0],
    })
    ok_or_exists("spawn DirectionalLight", r)

    for prop, val in [
        ("Intensity",           10.0),
        ("bAtmosphereSunLight", True),
        ("bUseTemperature",     True),
        ("Temperature",         3000.0),
    ]:
        r = send("set_actor_property", {
            "name": "SunLight",
            "property_name": prop,
            "property_value": val,
        })
        ok(f"SunLight.{prop} = {val}", r)

    # ── Player Start ─────────────────────────────────────────────────────────
    print("\n= Player start =")
    # 200 UU above floor clears the capsule half-height (96 UU) safely
    r = send("spawn_actor", {
        "name": "PlayerStart",
        "type": "PlayerStart",
        "location": [0.0, 0.0, 200.0],
        "rotation": [0.0, 0.0, 0.0],
    })
    ok_or_exists("spawn PlayerStart", r)

    # ── Save ─────────────────────────────────────────────────────────────────
    print("\n= Save level =")
    r = send("save_current_level", {})
    # save returns success=False with a note if level has no package path yet
    note = r.get("result", {}).get("note", "") if isinstance(r.get("result"), dict) else ""
    if note:
        print(f"  NOTE  save: {note}")
        print("        Use Ctrl+S in the UE5 editor to save the level.")
    else:
        ok("save_current_level", r)

    print("\nDone. Press Play in UE5 to test.")


if __name__ == "__main__":
    main()
