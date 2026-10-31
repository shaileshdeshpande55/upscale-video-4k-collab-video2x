"""Concurrent upload/process/download pipeline."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from api import ColabClient
from watcher import load_state, save_state


@dataclass
class JobResult:
    filename: str
    status: str  # completed | failed
    error: Optional[str] = None
    output_path: Optional[Path] = None


@dataclass
class Summary:
    completed: int = 0
    failed: int = 0
    results: list[JobResult] = field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        client: ColabClient,
        input_dir: Path,
        output_dir: Path,
        failed_dir: Path,
        state_path: Path,
        profile: str = "quality",
        codec: str = "libx264",
        crf: int = 18,
        poll_interval: float = 1.0,
        max_retries: int = 3,
        ui=None,
    ):
        self.client = client
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.failed_dir = failed_dir
        self.state_path = state_path
        self.profile = profile
        self.codec = codec
        self.crf = crf
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.ui = ui

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

        self.state = load_state(state_path)
        self._upload_q: asyncio.Queue = asyncio.Queue()
        self._process_q: asyncio.Queue = asyncio.Queue()
        self._download_q: asyncio.Queue = asyncio.Queue()
        self._stop = asyncio.Event()

    async def _retry(self, coro_factory, *args, **kwargs):
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                return await coro_factory(*args, **kwargs)
            except Exception as e:
                last_exc = e
                await asyncio.sleep(2 ** attempt)
        raise last_exc

    async def _poller(self):
        while True:
            item = await self._process_q.get()
            if item is None:
                await self._download_q.put(None)
                break
            f, job = item
            job_id = job["id"]
            terminal = False
            while not terminal:
                if self._stop.is_set():
                    break
                try:
                    job = await self.client.get_job(job_id)
                except Exception as e:
                    # backoff
                    await asyncio.sleep(min(10, self.poll_interval * 2))
                    continue
                status = job["status"]
                progress = job.get("progress", 0)
                fps = job.get("fps")
                eta = job.get("eta_seconds")
                if self.ui:
                    self.ui.update(f.name, status, progress, fps, eta)
                if status in ("completed", "failed", "canceled", "interrupted"):
                    terminal = True
                    if status == "completed":
                        await self._download_q.put((f, job))
                    else:
                        err = job.get("error") or status
                        self._move_failed(f)
                        self.state["failed"].append(f.name)
                        save_state(self.state_path, self.state)
                        if self.ui:
                            self.ui.update(f.name, "failed", progress, fps, err)
                else:
                    await asyncio.sleep(self.poll_interval)
            self._process_q.task_done()

    async def _downloader(self):
        while True:
            item = await self._download_q.get()
            if item is None:
                break
            f, job = item
            job_id = job["id"]
            out_name = (job.get("output") or {}).get("name") or f"{f.stem}_4k.mp4"
            dest = self.output_dir / out_name
            ok = False
            for attempt in range(self.max_retries):
                try:
                    if self.ui:
                        self.ui.update(f.name, "downloading", 0, None, None)
                    await self.client.download_job(job_id, dest, on_progress=lambda d, t: self.ui.update(f.name, "downloading", (d / t * 100) if t else 0, None, None) if self.ui else None)
                    ok = True
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        self._move_failed(f)
                        self.state["failed"].append(f.name)
                        save_state(self.state_path, self.state)
                        if self.ui:
                            self.ui.update(f.name, "failed", 0, None, str(e))
                        ok = False
                        break
                    await asyncio.sleep(2 ** attempt)
            if ok:
                # verify file exists and non-empty
                if dest.exists() and dest.stat().st_size > 0:
                    self.state["completed"].append(f.name)
                    self.state["in_progress"] = None
                    save_state(self.state_path, self.state)
                    # cleanup remote
                    try:
                        await self.client.delete_job(job_id)
                    except Exception:
                        pass
                    # remove original input
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if self.ui:
                        self.ui.update(f.name, "completed", 100, None, None)
                else:
                    self._move_failed(f)
                    self.state["failed"].append(f.name)
                    save_state(self.state_path, self.state)
                    if self.ui:
                        self.ui.update(f.name, "failed", 0, None, "download verification failed")
            self._download_q.task_done()

    def _move_failed(self, f: Path):
        try:
            dest = self.failed_dir / f.name
            if f.exists():
                shutil.move(str(f), str(dest))
        except Exception:
            pass

    async def run(self, files: list[Path]) -> Summary:
        # resume: skip completed
        files = [f for f in files if f.name not in set(self.state.get("completed", []))]

        # handle in_progress from previous run
        ip = self.state.get("in_progress")
        if ip:
            # check if output exists
            matches = list(self.output_dir.glob(f"{Path(ip).stem}_4k*"))
            if matches:
                self.state["completed"].append(ip)
            self.state["in_progress"] = None
            save_state(self.state_path, self.state)

        summary = Summary()
        if not files:
            return summary

        # feed upload queue
        async def feed():
            for f in files:
                await self._upload_q.put(f)
            await self._upload_q.put(None)

        async def uploader():
            for f in files:
                job = None
                for attempt in range(self.max_retries):
                    try:
                        self.state["in_progress"] = f.name
                        save_state(self.state_path, self.state)
                        if self.ui:
                            self.ui.update(f.name, "uploading", 0, None, None)
                        job = await self.client.upload_job(f, self.profile, self.codec, self.crf)
                        break
                    except Exception as e:
                        if attempt == self.max_retries - 1:
                            self._move_failed(f)
                            self.state["failed"].append(f.name)
                            save_state(self.state_path, self.state)
                            if self.ui:
                                self.ui.update(f.name, "failed", 0, None, str(e))
                            job = None
                            summary.failed += 1
                            summary.results.append(JobResult(f.name, "failed", str(e)))
                            break
                        await asyncio.sleep(2 ** attempt)
                if job is not None:
                    await self._process_q.put((f, job))
            await self._process_q.put(None)

        await asyncio.gather(
            uploader(),
            self._poller(),
            self._downloader(),
        )

        # tally
        for r in []:  # placeholder
            pass
        summary.completed = len(self.state.get("completed", []))
        summary.failed = len(self.state.get("failed", []))
        return summary
