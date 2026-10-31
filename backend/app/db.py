"""SQLite-backed job store."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models import Job, JobInput, JobOutput, JobStatus


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT '',
                    progress REAL NOT NULL DEFAULT 0,
                    frames_processed INTEGER NOT NULL DEFAULT 0,
                    frames_total INTEGER NOT NULL DEFAULT 0,
                    fps REAL,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    eta_seconds INTEGER,
                    input_json TEXT,
                    output_json TEXT,
                    profile TEXT NOT NULL DEFAULT 'quality',
                    codec TEXT NOT NULL DEFAULT 'libx264',
                    crf INTEGER NOT NULL DEFAULT 18,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        input_data = json.loads(row["input_json"]) if row["input_json"] else None
        output_data = json.loads(row["output_json"]) if row["output_json"] else None
        return Job(
            id=row["id"],
            status=JobStatus(row["status"]),
            phase=row["phase"] or "",
            progress=row["progress"],
            frames_processed=row["frames_processed"],
            frames_total=row["frames_total"],
            fps=row["fps"],
            elapsed_seconds=row["elapsed_seconds"],
            eta_seconds=row["eta_seconds"],
            input=JobInput(**input_data) if input_data else None,
            output=JobOutput(**output_data) if output_data else None,
            profile=row["profile"],
            codec=row["codec"],
            crf=row["crf"],
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            updated_at=row["updated_at"],
        )

    def create(self, job: Job) -> Job:
        with self._lock, self._conn() as conn:
            conn.execute(
                """INSERT INTO jobs (id,status,phase,progress,frames_processed,frames_total,fps,elapsed_seconds,eta_seconds,
                   input_json,output_json,profile,codec,crf,error,created_at,started_at,finished_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.id, job.status.value, job.phase, job.progress, job.frames_processed, job.frames_total,
                    job.fps, job.elapsed_seconds, job.eta_seconds,
                    job.input.model_dump_json() if job.input else None,
                    job.output.model_dump_json() if job.output else None,
                    job.profile, job.codec, job.crf, job.error,
                    job.created_at, job.started_at, job.finished_at, job.updated_at,
                ),
            )
            conn.commit()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self, limit: int = 50, status: Optional[str] = None) -> list[Job]:
        with self._lock, self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update(self, job_id: str, **fields) -> Optional[Job]:
        if not fields:
            return self.get(job_id)
        # Serialize nested objects
        if "input" in fields and fields["input"] is not None:
            fields["input_json"] = (
                fields["input"].model_dump_json() if hasattr(fields["input"], "model_dump_json")
                else json.dumps(fields["input"])
            )
            del fields["input"]
        if "output" in fields and fields["output"] is not None:
            fields["output_json"] = (
                fields["output"].model_dump_json() if hasattr(fields["output"], "model_dump_json")
                else json.dumps(fields["output"])
            )
            del fields["output"]
        if "status" in fields and hasattr(fields["status"], "value"):
            fields["status"] = fields["status"].value

        fields["updated_at"] = datetime.now(timezone.utc).isoformat()

        cols = ", ".join(f"{k}=?" for k in fields.keys())
        vals = list(fields.values()) + [job_id]
        with self._lock, self._conn() as conn:
            conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", vals)
            conn.commit()
        return self.get(job_id)

    def delete(self, job_id: str) -> bool:
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            conn.commit()
        return cur.rowcount > 0

    def mark_interrupted(self) -> int:
        active = ("queued", "probing", "processing", "resizing", "finalizing")
        placeholders = ",".join("?" for _ in active)
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                f"UPDATE jobs SET status='interrupted', updated_at=? WHERE status IN ({placeholders})",
                (datetime.now(timezone.utc).isoformat(), *active),
            )
            conn.commit()
        return cur.rowcount
