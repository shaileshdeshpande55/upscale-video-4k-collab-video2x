"""Configuration for the Video2X Colab backend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("V2X_DATA_DIR", "/content/video2x")))
    video2x_bin: str = field(default_factory=lambda: os.environ.get("V2X_VIDEO2X_BIN", "video2x"))
    api_token: str = field(default_factory=lambda: os.environ.get("API_TOKEN", os.environ.get("V2X_API_TOKEN", "")))
    allow_insecure: bool = field(default_factory=lambda: os.environ.get("V2X_ALLOW_INSECURE", "1").lower() in ("1", "true", "yes"))
    max_upload_bytes: int = field(default_factory=lambda: int(os.environ.get("V2X_MAX_UPLOAD_BYTES", str(4 * 1024 ** 3))))
    max_duration_seconds: int = field(default_factory=lambda: int(os.environ.get("V2X_MAX_DURATION_SECONDS", "600")))
    max_queue_size: int = field(default_factory=lambda: int(os.environ.get("V2X_MAX_QUEUE_SIZE", "3")))
    job_ttl_hours: int = field(default_factory=lambda: int(os.environ.get("V2X_JOB_TTL_HOURS", "24")))
    cors_origins: list[str] = field(default_factory=lambda: [o.strip() for o in os.environ.get("V2X_CORS_ORIGINS", "").split(",") if o.strip()])
    ngrok_token: str = field(default_factory=lambda: os.environ.get("NGROK_TOKEN", os.environ.get("V2X_NGROK_TOKEN", "")))
    port: int = field(default_factory=lambda: int(os.environ.get("V2X_PORT", "8000")))
    ffprobe_bin: str = field(default_factory=lambda: os.environ.get("V2X_FFPROBE_BIN", "ffprobe"))
    ffmpeg_bin: str = field(default_factory=lambda: os.environ.get("V2X_FFMPEG_BIN", "ffmpeg"))


def load_settings() -> Settings:
    return Settings()
