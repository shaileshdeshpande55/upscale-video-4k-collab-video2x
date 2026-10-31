"""Job manager: queue, worker thread, lifecycle."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Full
from typing import Callable, Optional

from app.config import Settings
from app.db import JobStore
from app.media import probe_video, validate_input
from app.models import Job, JobInput, JobOutput, JobStatus
from app.profiles import PROFILES, build_resize_command, build_video2x_command
from app.runner import run_video2x
from app.resizer import run_resize


class JobManager:
    def __init__(
        self,
        store: JobStore,
        settings: Settings,
        runner=run_video2x,
        resizer=run_resize,
        probe=probe_video,
    ):
        self.store = store
        self.settings = settings
        self.runner = runner
        self.resizer = resizer
        self.probe = probe
        self._queue: Queue[str] = Queue(maxsize=settings.max_queue_size)
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._running = True
        # recover interrupted
        self.store.mark_interrupted()
        self._worker.start()

    def shutdown(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)  # type: ignore
        except Exception:
            pass
        self._worker.join(timeout=5)

    def submit(
        self,
        file_path: Path,
        original_name: str,
        profile: str = "quality",
        codec: str = "libx264",
        crf: int = 18,
    ) -> Job:
        # capacity check
        if self._queue.full():
            raise RuntimeError("queue_full")
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            status=JobStatus.queued,
            phase="queued",
            profile=profile,
            codec=codec,
            crf=crf,
            input=JobInput(name=original_name, width=0, height=0, duration=0, size=file_path.stat().st_size),
        )
        # probe early for validation + storage
        try:
            info = self.probe(file_path, self.settings.ffprobe_bin)
        except Exception as e:
            job.status = JobStatus.failed
            job.error = f"probe failed: {e}"
            self.store.create(job)
            raise
        validate_input(info, self.settings.max_duration_seconds, self.settings.max_upload_bytes)
        # storage check
        try:
            free = self._free_disk()
        except Exception:
            free = 0
        if free and free < info.size * 4:
            job.status = JobStatus.failed
            job.error = "insufficient storage"
            self.store.create(job)
            raise RuntimeError("insufficient_storage")

        job.input = JobInput(
            name=original_name, width=info.width, height=info.height,
            duration=info.duration, size=info.size,
        )
        self.store.create(job)
        ev = threading.Event()
        with self._lock:
            self._cancel_events[job_id] = ev
        self._queue.put(job_id)
        # stash file path + params on job via a sidecar dict
        with self._lock:
            self._job_files[job_id] = (file_path, profile, codec, crf)
        return job

    def _free_disk(self) -> int:
        import shutil
        return shutil.disk_usage(str(self.settings.data_dir)).free

    # sidecar storage
    _job_files: dict = {}

    def cancel(self, job_id: str) -> Optional[Job]:
        job = self.store.get(job_id)
        if job is None:
            return None
        if job.status in (JobStatus.completed, JobStatus.failed, JobStatus.canceled, JobStatus.interrupted):
            return job
        ev = self._cancel_events.get(job_id)
        if ev is not None:
            ev.set()
        # if queued, mark canceled immediately
        if job.status == JobStatus.queued:
            self.store.update(job_id, status=JobStatus.canceled, phase="canceled",
                              finished_at=datetime.now(timezone.utc).isoformat())
        return self.store.get(job_id)

    def _worker_loop(self) -> None:
        while self._running:
            try:
                job_id = self._queue.get(timeout=1)
            except Exception:
                continue
            if job_id is None:
                break
            self._process_job(job_id)

    def _process_job(self, job_id: str) -> None:
        with self._lock:
            info = self._job_files.get(job_id)
        if info is None:
            self.store.update(job_id, status=JobStatus.failed, error="missing job file")
            return
        file_path, profile, codec, crf = info
        job = self.store.get(job_id)
        if job is None or job.status == JobStatus.canceled:
            return

        cancel_event = self._cancel_events.get(job_id, threading.Event())

        # probing
        self.store.update(job_id, status=JobStatus.probing, phase="probing",
                          started_at=datetime.now(timezone.utc).isoformat())

        try:
            vinfo = self.probe(file_path, self.settings.ffprobe_bin)
        except Exception as e:
            self.store.update(job_id, status=JobStatus.failed, phase="failed", error=str(e),
                              finished_at=datetime.now(timezone.utc).isoformat())
            return

        job_dir = self.settings.data_dir / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        input_path = job_dir / ("input" + file_path.suffix)
        # copy/link
        try:
            import shutil
            shutil.copy2(file_path, input_path)
        except Exception as e:
            self.store.update(job_id, status=JobStatus.failed, error=f"copy failed: {e}")
            return

        spec_profile = profile
        intermediate = job_dir / "intermediate.mp4"
        output_path = job_dir / "output.mp4"

        # progress callback
        def on_v2x_progress(upd):
            # map 2..92% for quality, 2..98% for one-pass
            needs_resize = (spec_profile == "quality")
            hi = 92.0 if needs_resize else 98.0
            pct = 2.0 + (upd.percent / 100.0) * (hi - 2.0)
            self.store.update(
                job_id, status=JobStatus.processing, phase="upscaling",
                progress=pct, frames_processed=upd.frames_processed,
                frames_total=upd.frames_total, fps=upd.fps,
                elapsed_seconds=upd.elapsed_seconds, eta_seconds=upd.eta_seconds,
            )

        # upscaling
        self.store.update(job_id, status=JobStatus.processing, phase="upscaling", progress=2.0)
        cmd = build_video2x_command(spec_profile, input_path, intermediate if (spec_profile == "quality") else output_path,
                                    self.settings, codec, crf)
        # For non-quality profiles, output directly to output_path
        if spec_profile != "quality":
            cmd = build_video2x_command(spec_profile, input_path, output_path, self.settings, codec, crf)

        result = self.runner(cmd, on_progress=on_v2x_progress, cancel_event=cancel_event)
        if cancel_event.is_set():
            self.store.update(job_id, status=JobStatus.canceled, phase="canceled",
                              finished_at=datetime.now(timezone.utc).isoformat())
            return
        if result.returncode != 0:
            self.store.update(job_id, status=JobStatus.failed, phase="failed",
                              error=result.stderr_tail or "video2x failed",
                              finished_at=datetime.now(timezone.utc).isoformat())
            return

        # resize pass for quality profile
        if spec_profile == "quality":
            self.store.update(job_id, status=JobStatus.resizing, phase="resizing", progress=92.0)
            try:
                oinfo = self.probe(intermediate, self.settings.ffprobe_bin)
            except Exception as e:
                self.store.update(job_id, status=JobStatus.failed, error=f"probe intermediate: {e}")
                return
            resize_cmd = build_resize_command(intermediate, output_path, self.settings, crf, codec)

            def on_resize_progress(pct):
                mapped = 92.0 + (pct / 100.0) * 6.0
                self.store.update(job_id, status=JobStatus.resizing, phase="resizing", progress=mapped)

            r2 = self.resizer(resize_cmd, vinfo.duration, on_progress=on_resize_progress, cancel_event=cancel_event)
            if cancel_event.is_set():
                self.store.update(job_id, status=JobStatus.canceled, phase="canceled",
                                  finished_at=datetime.now(timezone.utc).isoformat())
                return
            if r2.returncode != 0:
                self.store.update(job_id, status=JobStatus.failed, phase="failed",
                                  error=r2.stderr_tail or "resize failed",
                                  finished_at=datetime.now(timezone.utc).isoformat())
                return
            try:
                intermediate.unlink(missing_ok=True)
            except Exception:
                pass

        # finalizing
        self.store.update(job_id, status=JobStatus.finalizing, phase="finalizing", progress=98.0)
        try:
            out_info = self.probe(output_path, self.settings.ffprobe_bin)
        except Exception as e:
            self.store.update(job_id, status=JobStatus.failed, error=f"probe output: {e}")
            return

        out_name = f"{Path(vinfo and 'out' or 'out').name}"  # placeholder
        # better output name from job input
        job = self.store.get(job_id)
        base = Path(job.input.name).stem if job and job.input else "output"
        out_name = f"{base}_4k.mp4"

        self.store.update(
            job_id, status=JobStatus.completed, phase="completed", progress=100.0,
            output=JobOutput(name=out_name, width=out_info.width, height=out_info.height,
                             size=output_path.stat().st_size),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        # store output path sidecar
        with self._lock:
            self._output_paths[job_id] = output_path

    _output_paths: dict = {}

    def output_path(self, job_id: str) -> Optional[Path]:
        with self._lock:
            p = self._output_paths.get(job_id)
        if p is not None:
            return p
        # fallback
        p = self.settings.data_dir / "jobs" / job_id / "output.mp4"
        return p if p.exists() else None
