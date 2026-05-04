"""
Hunyuan3D-2.1 pipeline adapter.

VRAM sequencing (SD Forge removed — all models run as short-lived subprocesses):
  1. If reference_image supplied → use it directly (skip generation)
     Else → spawn generate_image.py subprocess → PNG → subprocess exits → VRAM free
  2. Spawn HY3D api_server subprocess (has full VRAM)
  3. Wait for HY3D ready, submit PNG → job_id
  4. Poll HY3D /status/{uid} → textured GLB
  5. Kill HY3D subprocess, save outputs

SD Forge is NOT used or managed by this adapter.

Listens on 0.0.0.0:8188.

Environment:
  HY3D_SERVER          HY3D api_server URL        (default http://localhost:8081)
  HY3D_SEED            Seed for reproducibility   (default 1234)
  HY3D_PYTHON          Path to HY3D's python.exe
  HY3D_DIR             Working directory of api_server.py
  HY3D_MODEL_PATH      Hunyuan3D-2.1 model root
  HY3D_SUBFOLDER       Model subfolder            (default hunyuan3d-dit-v2-1)
  HY3D_CACHE_PATH      HY3D cache directory
  SD_MODEL_PATH        Local .safetensors for image gen
                       (default: juggernautXL in sd-webui-forge-neo models dir)
"""
import asyncio
import base64
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── config ─────────────────────────────────────────────────────────────────

HY3D_SERVER   = os.environ.get("HY3D_SERVER",   "http://localhost:8081")
HY3D_SEED     = int(os.environ.get("HY3D_SEED", "1234"))
LISTEN_PORT   = int(os.environ.get("HY3D_ADAPTER_PORT", "8188"))

HY3D_PYTHON     = os.environ.get("HY3D_PYTHON",
    r"C:\AI\HY3D2\Hunyuan3D2_WinPortable\python_standalone\python.exe")
HY3D_DIR        = os.environ.get("HY3D_DIR",
    r"C:\AI\HY3D2\Hunyuan3D2_WinPortable\Hunyuan3D-2.1")
HY3D_MODEL_PATH = os.environ.get("HY3D_MODEL_PATH",
    r"E:\hunyuan3d\models\Hunyuan3D-2.1")
HY3D_SUBFOLDER  = os.environ.get("HY3D_SUBFOLDER", "hunyuan3d-dit-v2-1")
HY3D_CACHE_PATH = os.environ.get("HY3D_CACHE_PATH", r"E:\hunyuan3d\cache")

SD_MODEL_PATH = os.environ.get(
    "SD_MODEL_PATH",
    r"D:\sd-webui-forge-neo\models\Stable-diffusion\juggernautXL_ragnarokBy.safetensors",
)

# This script lives next to hunyuan3d_server.py
_GENERATE_IMAGE_SCRIPT = str(Path(__file__).parent / "generate_image.py")

# ── state ───────────────────────────────────────────────────────────────────

_jobs: dict[str, dict] = {}
_hy3d_proc: Optional[subprocess.Popen] = None
_hy3d_lock = asyncio.Lock()

app = FastAPI(title="Hunyuan3D pipeline adapter", version="2.0.0")


# ── models ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    output_dir: str
    # Supply a path to skip image generation and use your own reference image.
    # Supports local file paths (absolute or relative to output_dir).
    reference_image: Optional[str] = None
    seed: Optional[int] = None
    octree_resolution: int = 256
    num_inference_steps: int = 5
    guidance_scale: float = 5.0
    # Set to True to run the full paint pipeline (DINOv2/CLIP/SDXL ~13 GB extra VRAM).
    # Defaults to False to stay within 24 GB budget with the DiT alone.
    texture: bool = False


# ── image generation (Option A) ─────────────────────────────────────────────

async def _generate_image(prompt: str, seed: int, out_path: Path) -> None:
    """
    Spawn generate_image.py as a subprocess using HY3D's Python.
    The process exits after saving the PNG, freeing all GPU memory.
    """
    cmd = [
        HY3D_PYTHON,
        _GENERATE_IMAGE_SCRIPT,
        prompt,
        str(out_path),
        str(seed),
        SD_MODEL_PATH,
    ]
    log_path = out_path.with_suffix(".imggen.log")
    with open(log_path, "w") as lf:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=lf,
            stderr=lf,
        )
        retcode = await proc.wait()

    if retcode != 0:
        log_tail = log_path.read_text(errors="replace")[-2000:]
        raise RuntimeError(f"generate_image.py failed (code {retcode}):\n{log_tail}")


# ── HY3D subprocess management ──────────────────────────────────────────────

def _pid_on_port(port: int) -> Optional[int]:
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                return int(line.strip().split()[-1])
    except Exception:
        pass
    return None


def _kill_pid(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=10)
    except Exception:
        pass


async def _kill_hy3d() -> None:
    global _hy3d_proc
    if _hy3d_proc is not None:
        try:
            _hy3d_proc.terminate()
            try:
                _hy3d_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _hy3d_proc.kill()
        except Exception:
            pass
        _hy3d_proc = None
    pid = _pid_on_port(8081)
    if pid:
        _kill_pid(pid)
    await asyncio.sleep(2)


async def _start_hy3d() -> None:
    global _hy3d_proc
    await _kill_hy3d()

    Path(HY3D_DIR, "gradio_cache").mkdir(parents=True, exist_ok=True)

    cmd = [
        HY3D_PYTHON, "api_server.py",
        "--model_path", HY3D_MODEL_PATH,
        "--subfolder",  HY3D_SUBFOLDER,
        "--cache-path", HY3D_CACHE_PATH,
        "--port",       "8081",
    ]
    hy3d_log = Path(HY3D_DIR, "gradio_cache", "api_server.log")
    _hy3d_proc = subprocess.Popen(
        cmd,
        cwd=HY3D_DIR,
        stdout=open(hy3d_log, "w"),
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 600  # 10 min max
    while time.time() < deadline:
        if _hy3d_proc.poll() is not None:
            log_tail = hy3d_log.read_text(errors="replace")[-3000:] if hy3d_log.exists() else ""
            raise RuntimeError(
                f"HY3D api_server exited (code {_hy3d_proc.returncode}):\n{log_tail}"
            )
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(f"{HY3D_SERVER}/health")
                if r.status_code < 500:
                    return
        except Exception:
            pass
        await asyncio.sleep(5)

    raise TimeoutError("HY3D api_server did not become ready within 10 minutes")


# ── HY3D API calls ───────────────────────────────────────────────────────────

async def _hy3d_send(image_bytes: bytes, params: dict) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "image": b64,
        "texture": params.get("texture", False),
        "seed": params.get("seed", HY3D_SEED),
        "octree_resolution": params.get("octree_resolution", 256),
        "num_inference_steps": params.get("num_inference_steps", 5),
        "guidance_scale": params.get("guidance_scale", 5.0),
        "remove_background": True,
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{HY3D_SERVER}/send", json=payload)
        r.raise_for_status()
    return r.json()["uid"]


async def _hy3d_status(uid: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{HY3D_SERVER}/status/{uid}")
        r.raise_for_status()
    return r.json()


# ── texture extraction ───────────────────────────────────────────────────────

def _extract_textures(glb_bytes: bytes, output_dir: str, stem: str) -> dict[str, str]:
    paths: dict[str, str] = {}
    glb_path = Path(output_dir) / f"{stem}.glb"
    glb_path.write_bytes(glb_bytes)
    paths["glb_path"] = str(glb_path)

    try:
        from pygltflib import GLTF2
        gltf = GLTF2().load(str(glb_path))
        for i, img in enumerate(gltf.images or []):
            if img.bufferView is None:
                continue
            bv   = gltf.bufferViews[img.bufferView]
            buf  = gltf.buffers[bv.buffer]
            data = (gltf.get_data_from_buffer_uri(buf.uri) if buf.uri
                    else gltf._glb_data)  # type: ignore[attr-defined]
            raw  = data[bv.byteOffset: bv.byteOffset + bv.byteLength]
            label = (img.name or f"texture_{i}").lower()
            key   = ("normal_path" if "normal" in label
                     else "orm_path" if any(x in label for x in ("metal","rough","orm","pbr"))
                     else "albedo_path")
            out_path = str(Path(output_dir) / f"{stem}_{key.split('_')[0]}.png")
            Path(out_path).write_bytes(raw)
            paths.setdefault(key, out_path)
    except Exception:
        pass

    return paths


# ── job runner ───────────────────────────────────────────────────────────────

async def _run_job(job_id: str, req: GenerateRequest):
    seed = req.seed if req.seed is not None else HY3D_SEED
    out  = Path(req.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    async with _hy3d_lock:
        try:
            # ── Stage 1: acquire reference image ────────────────────────────
            if req.reference_image:
                # Option C: user-supplied image
                ref = Path(req.reference_image)
                if not ref.is_absolute():
                    ref = out / req.reference_image
                if not ref.exists():
                    raise FileNotFoundError(f"reference_image not found: {ref}")
                img_bytes = ref.read_bytes()
                _jobs[job_id]["reference_image"] = str(ref)
                _jobs[job_id]["status"] = "using_reference_image"
            else:
                # Option A: generate via diffusers subprocess
                _jobs[job_id]["status"] = "generating_image"
                ref_png = out / f"{job_id}_reference.png"
                await _generate_image(req.prompt, seed, ref_png)
                img_bytes = ref_png.read_bytes()
                _jobs[job_id]["reference_image"] = str(ref_png)

            # ── Stage 2: spawn HY3D (VRAM is clear — image gen subprocess exited) ──
            _jobs[job_id]["status"] = "starting_hy3d"
            await _start_hy3d()

            # ── Stage 3: submit image ────────────────────────────────────────
            _jobs[job_id]["status"] = "generating_3d"
            hy3d_uid = await _hy3d_send(img_bytes, {
                "seed": seed,
                "octree_resolution": req.octree_resolution,
                "num_inference_steps": req.num_inference_steps,
                "guidance_scale": req.guidance_scale,
                "texture": req.texture,
            })
            _jobs[job_id]["hy3d_uid"] = hy3d_uid

            # ── Stage 4: poll until done ─────────────────────────────────────
            _jobs[job_id]["status"] = "texturing"
            deadline = time.time() + 1200
            while time.time() < deadline:
                st = await _hy3d_status(hy3d_uid)
                if st["status"] == "completed":
                    glb_b64   = st.get("model_base64", "")
                    glb_bytes = base64.b64decode(glb_b64) if glb_b64 else b""
                    break
                if st["status"] == "error":
                    raise RuntimeError(f"HY3D error: {st}")
                await asyncio.sleep(5)
            else:
                raise TimeoutError("HY3D timed out after 20 min")

            # ── Stage 5: save ────────────────────────────────────────────────
            result = _extract_textures(glb_bytes, str(out), job_id)
            _jobs[job_id].update({"status": "complete", **result})

        except Exception as exc:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"]  = str(exc)

        finally:
            await _kill_hy3d()


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":       "ok",
        "hy3d_running": _pid_on_port(8081) is not None,
        "hy3d_url":     HY3D_SERVER,
        "sd_model":     Path(SD_MODEL_PATH).name if Path(SD_MODEL_PATH).exists() else "not found",
    }


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued", "hy3d_uid": None}
    asyncio.create_task(_run_job(job_id, req))
    return JSONResponse({"job_id": job_id}, status_code=202)


@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail="Unknown job_id")
    return JSONResponse(job)


@app.post("/api/v1/unload")
async def unload():
    """Kill HY3D if running (frees all VRAM)."""
    await _kill_hy3d()
    return {"status": "ok"}


# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sd_status = "found" if Path(SD_MODEL_PATH).exists() else "not found (will download SD 1.5)"
    print(f"HY3D adapter  v2.0  on 0.0.0.0:{LISTEN_PORT}")
    print(f"  HY3D      : {HY3D_SERVER} (spawned per job)")
    print(f"  SD model  : {Path(SD_MODEL_PATH).name}  [{sd_status}]")
    print(f"  No SD Forge required.")
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
