"""
Thin Mixamo HTTP client for the asset pipeline.

Mixamo's API is community-reverse-engineered; treat this as best-effort
glue. If endpoints shift upstream, update _ENDPOINTS and the field names
in _Result.

Auth: Adobe IMS bearer token, cached at --token (default ~/.mixamo/token.json).
First-ever run requires the user to obtain a token via browser-based OAuth
and drop the JSON at the cache path. Token refresh on 401 is best-effort —
on hard failure we tell the user to re-auth.

Usage:
    python mixamo_client.py rig --input <fbx> --output <fbx> [--token <path>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests


# --- API surface --------------------------------------------------------------

_ENDPOINTS = {
    "upload":         "https://www.mixamo.com/api/v1/character/uploads",
    "upload_status":  "https://www.mixamo.com/api/v1/character/uploads/{upload_id}",
    "rig":            "https://www.mixamo.com/api/v1/character/{character_id}/rig",
    "rig_status":     "https://www.mixamo.com/api/v1/character/{character_id}/rig",
    "download":       "https://www.mixamo.com/api/v1/character/{character_id}/download",
    "ims_refresh":    "https://ims-na1.adobelogin.com/ims/token/v3",
}

_POLL_INTERVAL_SEC = 5
_POLL_TIMEOUT_SEC = 600  # 10 min — Mixamo rigging takes 1-3 min typically


@dataclass
class _Result:
    ok: bool
    message: str
    output_path: str | None = None
    reason: str | None = None  # set when ok=False to explain skip vs error


def _load_token(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        raise SystemExit(
            f"Mixamo token cache not found at {p}.\n"
            f"First-time setup: log into mixamo.com in a browser, copy the\n"
            f"IMS bearer token from devtools, and write JSON: "
            f'{{"access_token": "...", "refresh_token": "...", "expires_at": <unix>}}'
        )
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_token(path: str, token: dict) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2)


def _refresh_if_needed(token: dict, path: str) -> dict:
    if token.get("expires_at", 0) > time.time() + 60:
        return token
    refresh = token.get("refresh_token")
    if not refresh:
        raise SystemExit("Mixamo token expired and no refresh_token cached — re-auth required.")
    resp = requests.post(_ENDPOINTS["ims_refresh"], data={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": token.get("client_id", "MixamoWeb1"),
    }, timeout=30)
    resp.raise_for_status()
    new = resp.json()
    token["access_token"] = new["access_token"]
    token["expires_at"] = int(time.time()) + int(new.get("expires_in", 3600))
    if "refresh_token" in new:
        token["refresh_token"] = new["refresh_token"]
    _save_token(path, token)
    return token


def _auth_headers(token: dict) -> dict:
    return {"Authorization": f"Bearer {token['access_token']}"}


def _retry(call, *, label: str, attempts: int = 3):
    """Exponential backoff: 2s/4s/8s. Retries on connection errors and 5xx."""
    last_exc = None
    for i in range(attempts):
        try:
            r = call()
            if 500 <= r.status_code < 600:
                raise requests.HTTPError(f"{label}: HTTP {r.status_code}")
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last_exc = exc
            if i == attempts - 1:
                break
            time.sleep(2 ** (i + 1))
    raise SystemExit(f"{label} failed after {attempts} attempts: {last_exc}")


# --- Operations ---------------------------------------------------------------

def rig(input_fbx: str, output_fbx: str, token_path: str) -> _Result:
    if not os.path.isfile(input_fbx):
        return _Result(False, f"input FBX not found: {input_fbx}", reason="missing_input")

    token = _refresh_if_needed(_load_token(token_path), token_path)
    headers = _auth_headers(token)

    # 1. Upload.
    with open(input_fbx, "rb") as f:
        upload = _retry(
            lambda: requests.post(_ENDPOINTS["upload"], headers=headers,
                                  files={"file": (os.path.basename(input_fbx), f)},
                                  timeout=120),
            label="upload",
        )
    if upload.status_code >= 400:
        return _Result(False, f"upload rejected: HTTP {upload.status_code} {upload.text[:300]}",
                       reason="upload_rejected")
    upload_id = upload.json().get("id") or upload.json().get("upload_id")
    if not upload_id:
        return _Result(False, f"upload response missing id: {upload.text[:300]}",
                       reason="api_shape_changed")

    # 2. Wait for analysis. Mixamo decides if the upload is humanoid.
    deadline = time.time() + _POLL_TIMEOUT_SEC
    character_id = None
    while time.time() < deadline:
        status = _retry(
            lambda: requests.get(_ENDPOINTS["upload_status"].format(upload_id=upload_id),
                                 headers=headers, timeout=30),
            label="upload_status",
        )
        body = status.json() if status.headers.get("content-type", "").startswith("application/json") else {}
        st = body.get("status")
        if st == "analysis_complete":
            character_id = body.get("character_id") or body.get("id")
            break
        if st in ("failed", "rejected"):
            reason = body.get("error", "Mixamo rejected the upload (likely non-humanoid)")
            return _Result(False, reason, reason="not_humanoid")
        time.sleep(_POLL_INTERVAL_SEC)
    else:
        return _Result(False, "Mixamo analysis timed out", reason="timeout")

    # 3. Trigger rig.
    _retry(
        lambda: requests.post(_ENDPOINTS["rig"].format(character_id=character_id),
                              headers=headers,
                              json={"skeleton": "standard", "fingers": True},
                              timeout=60),
        label="rig",
    )

    # 4. Wait for rig completion.
    deadline = time.time() + _POLL_TIMEOUT_SEC
    while time.time() < deadline:
        status = _retry(
            lambda: requests.get(_ENDPOINTS["rig_status"].format(character_id=character_id),
                                 headers=headers, timeout=30),
            label="rig_status",
        )
        body = status.json() if status.headers.get("content-type", "").startswith("application/json") else {}
        if body.get("status") == "rigging_complete":
            break
        if body.get("status") in ("failed", "rejected"):
            return _Result(False, body.get("error", "rigging failed"), reason="rig_failed")
        time.sleep(_POLL_INTERVAL_SEC)
    else:
        return _Result(False, "Mixamo rigging timed out", reason="timeout")

    # 5. Download rigged FBX.
    download = _retry(
        lambda: requests.get(_ENDPOINTS["download"].format(character_id=character_id),
                             headers=headers, params={"format": "fbx"}, timeout=300),
        label="download",
    )
    if download.status_code >= 400:
        return _Result(False, f"download failed: HTTP {download.status_code}", reason="download_failed")

    Path(output_fbx).parent.mkdir(parents=True, exist_ok=True)
    with open(output_fbx, "wb") as f:
        f.write(download.content)

    return _Result(True, "rigged", output_path=output_fbx)


# --- CLI ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Mixamo auto-rig client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rig_p = sub.add_parser("rig")
    rig_p.add_argument("--input", required=True)
    rig_p.add_argument("--output", required=True)
    rig_p.add_argument("--token", default=os.path.expanduser("~/.mixamo/token.json"))

    args = parser.parse_args()
    if args.cmd == "rig":
        result = rig(args.input, args.output, args.token)
        # Print a JSON line so the slash command can parse the outcome
        # without relying on stderr ordering.
        print(json.dumps({
            "ok": result.ok,
            "message": result.message,
            "output": result.output_path,
            "reason": result.reason,
        }))
        sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
