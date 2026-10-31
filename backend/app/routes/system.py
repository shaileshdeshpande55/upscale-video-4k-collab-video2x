"""System info route."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/system")
async def system_info(request: Request):
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        from app.config import load_settings
        settings = load_settings()
    manager = getattr(request.app.state, "job_manager", None)
    gpu = "unknown"
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            gpu = r.stdout.strip().splitlines()[0]
    except Exception:
        pass
    free_disk = 0
    try:
        free_disk = shutil.disk_usage(str(settings.data_dir)).free
    except Exception:
        pass
    queue_depth = 0
    if manager is not None:
        queue_depth = manager._queue.qsize()
    return {
        "status": "ok",
        "gpu": gpu,
        "free_disk_bytes": free_disk,
        "queue_depth": queue_depth,
        "max_upload_bytes": settings.max_upload_bytes,
        "max_duration_seconds": settings.max_duration_seconds,
        "max_queue_size": settings.max_queue_size,
        "profiles": ["quality", "anime", "fast"],
    }
