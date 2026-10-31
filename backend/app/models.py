"""Pydantic models and enums for jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    probing = "probing"
    processing = "processing"
    resizing = "resizing"
    finalizing = "finalizing"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"
    interrupted = "interrupted"


class Profile(str, Enum):
    quality = "quality"
    anime = "anime"
    fast = "fast"


class VideoInfo(BaseModel):
    width: int
    height: int
    duration: float
    size: int
    codec: Optional[str] = None
    fps: Optional[float] = None


class JobInput(BaseModel):
    name: str
    width: int
    height: int
    duration: float
    size: int


class JobOutput(BaseModel):
    name: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[int] = None


class Job(BaseModel):
    id: str
    status: JobStatus
    phase: str = ""
    progress: float = 0.0
    frames_processed: int = 0
    frames_total: int = 0
    fps: Optional[float] = None
    elapsed_seconds: int = 0
    eta_seconds: Optional[int] = None
    input: Optional[JobInput] = None
    output: Optional[JobOutput] = None
    profile: str = "quality"
    codec: str = "libx264"
    crf: int = 18
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
