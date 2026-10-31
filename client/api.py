"""Async HTTP client for the Colab backend."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Optional

import httpx


class ColabClient:
    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.token = token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "ngrok-skip-browser-warning": "1",
                "User-Agent": "Video2X-CLI/1.0",
            },
        )

    async def close(self):
        await self._client.aclose()

    def _auth_headers(self) -> dict:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    async def health(self) -> dict:
        r = await self._client.get("/healthz")
        r.raise_for_status()
        return r.json()

    async def system(self) -> dict:
        r = await self._client.get("/api/system", headers=self._auth_headers())
        r.raise_for_status()
        return r.json()

    async def profiles(self) -> list:
        r = await self._client.get("/api/profiles") if False else None
        # profiles not a separate endpoint; return static
        return ["quality", "anime", "fast"]

    async def upload_job(
        self,
        file_path: Path,
        profile: str = "quality",
        codec: str = "libx264",
        crf: int = 18,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        url = "/api/jobs"
        file_size = file_path.stat().st_size

        def gen():
            with file_path.open("rb") as f:
                uploaded = 0
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    uploaded += len(chunk)
                    if on_progress:
                        on_progress(uploaded, file_size)
                    yield chunk

        files = {"file": (file_path.name, file_path.open("rb"), "application/octet-stream")}
        data = {"profile": profile, "codec": codec, "crf": str(crf)}
        r = await self._client.post(url, files=files, data=data, headers=self._auth_headers())
        r.raise_for_status()
        return r.json()

    async def get_job(self, job_id: str) -> dict:
        r = await self._client.get(f"/api/jobs/{job_id}", headers=self._auth_headers())
        r.raise_for_status()
        return r.json()

    async def list_jobs(self, limit: int = 20) -> list:
        r = await self._client.get("/api/jobs", params={"limit": limit}, headers=self._auth_headers())
        r.raise_for_status()
        return r.json()

    async def cancel_job(self, job_id: str) -> dict:
        r = await self._client.post(f"/api/jobs/{job_id}/cancel", headers=self._auth_headers())
        r.raise_for_status()
        return r.json()

    async def delete_job(self, job_id: str) -> None:
        r = await self._client.delete(f"/api/jobs/{job_id}", headers=self._auth_headers())
        r.raise_for_status()

    async def download_job(
        self,
        job_id: str,
        dest_path: Path,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        # get job for filename
        job = await self.get_job(job_id)
        url = f"/api/jobs/{job_id}/download"
        async with self._client.stream("GET", url, headers=self._auth_headers()) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            tmp = dest_path.with_suffix(dest_path.suffix + ".part")
            with tmp.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total)
            # atomic rename
            os_replace = __import__("os").replace
            os_replace(str(tmp), str(dest_path))
