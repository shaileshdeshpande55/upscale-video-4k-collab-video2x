"""Media probing and validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from app.models import VideoInfo


def probe_video(path: Path, ffprobe_bin: str = "ffprobe") -> VideoInfo:
    cmd = [
        ffprobe_bin, "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    video_stream = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            video_stream = s
            break
    if video_stream is None:
        raise ValueError("No video stream found")
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", video_stream.get("duration", 0)))
    size = int(fmt.get("size", path.stat().st_size))
    width = int(video_stream["width"])
    height = int(video_stream["height"])
    codec = video_stream.get("codec_name")
    fps = None
    r_frame_rate = video_stream.get("r_frame_rate", "")
    if "/" in r_frame_rate:
        num, den = r_frame_rate.split("/")
        if int(den) != 0:
            fps = int(num) / int(den)
    return VideoInfo(width=width, height=height, duration=duration, size=size, codec=codec, fps=fps)


def validate_input(info: VideoInfo, max_duration: int, max_size: int) -> None:
    if info.duration <= 0:
        raise ValueError("Invalid duration")
    if info.duration > max_duration:
        raise ValueError(f"Duration {info.duration}s exceeds limit {max_duration}s")
    if info.size > max_size:
        raise ValueError(f"File size {info.size} exceeds limit {max_size}")
    if info.width <= 0 or info.height <= 0:
        raise ValueError("Invalid dimensions")
