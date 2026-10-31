"""Job routes."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.auth import make_auth
from app.config import Settings
from app.jobs import JobManager
from app.models import Job, Profile

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _manager(request: Request) -> JobManager:
    m = getattr(request.app.state, "job_manager", None)
    if m is None:
        raise HTTPException(status_code=503, detail="Job manager not available")
    return m


def _settings(request: Request) -> Settings:
    s = getattr(request.app.state, "settings", None)
    if s is None:
        from app.config import load_settings
        s = load_settings()
        request.app.state.settings = s
    return s


@router.post("", status_code=201)
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    profile: str = Form("quality"),
    codec: str = Form("libx264"),
    crf: int = Form(18),
):
    settings: Settings = _settings(request)
    manager = _manager(request)

    # validate profile
    if profile not in ("quality", "anime", "fast"):
        raise HTTPException(status_code=422, detail="invalid profile")

    # storage: save upload to temp job dir after creating job
    job_dir = settings.data_dir / "uploads" / "tmp"
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "input.mp4").name
    dest = job_dir / safe_name

    # enforce size while streaming
    max_bytes = settings.max_upload_bytes
    total = 0
    with dest.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="upload too large")
            f.write(chunk)

    # storage check
    import shutil as _sh
    free = _sh.disk_usage(str(settings.data_dir)).free
    if free < total * 4:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=507, detail="insufficient storage")

    try:
        job = manager.submit(dest, safe_name, profile=profile, codec=codec, crf=crf)
    except RuntimeError as e:
        dest.unlink(missing_ok=True)
        if str(e) == "queue_full":
            raise HTTPException(status_code=429, detail="queue full")
        if str(e) == "insufficient_storage":
            raise HTTPException(status_code=507, detail="insufficient storage")
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))

    return job


@router.get("")
async def list_jobs(request: Request, limit: int = 20, status: str | None = None):
    manager = _manager(request)
    jobs = manager.store.list_jobs(limit=limit, status=status)
    return [j.model_dump() for j in jobs]


@router.get("/{job_id}")
async def get_job(request: Request, job_id: str):
    manager = _manager(request)
    job = manager.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@router.post("/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str):
    manager = _manager(request)
    job = manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@router.delete("/{job_id}")
async def delete_job(request: Request, job_id: str):
    manager = _manager(request)
    job = manager.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in ("processing", "resizing", "probing", "finalizing"):
        raise HTTPException(status_code=409, detail="job still running")
    # remove files
    job_dir = _settings(request).data_dir / "jobs" / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    manager.store.delete(job_id)
    return {"deleted": True}


@router.get("/{job_id}/logs")
async def job_logs(request: Request, job_id: str, tail: int = 200):
    manager = _manager(request)
    job = manager.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    job_dir = _settings(request).data_dir / "jobs" / job_id
    log_path = job_dir / "job.log"
    if not log_path.exists():
        return {"lines": []}
    lines = log_path.read_text(errors="replace").splitlines()
    return {"lines": lines[-tail:]}
