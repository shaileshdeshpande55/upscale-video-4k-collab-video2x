"""Range-aware file download."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

router = APIRouter(prefix="/api/jobs", tags=["files"])


@router.get("/{job_id}/download")
async def download_job(request: Request, job_id: str):
    from app.jobs import JobManager

    manager: JobManager = request.app.state.job_manager
    settings = request.app.state.settings
    job = manager.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="job not completed")

    path = manager.output_path(job_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="output not found")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        # parse "bytes=start-end"
        try:
            unit, rng = range_header.split("=", 1)
            start_str, end_str = rng.split("-", 1)
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except Exception:
            start, end = 0, file_size - 1
        start = max(0, start)
        end = min(file_size - 1, end)
        if start > end:
            raise HTTPException(status_code=416, detail="range not satisfiable")
        length = end - start + 1

        def gen():
            with path.open("rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            gen(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Disposition": f'attachment; filename="{path.name}"',
            },
        )

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=job.output.name if (job.output and job.output.name) else path.name,
    )
