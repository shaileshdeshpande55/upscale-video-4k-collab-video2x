"""Progress parsing for Video2X and ffmpeg output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# frame=123/456 (26.97%); fps=1.23; elapsed=00:01:40; remaining=00:04:32
PROGRESS_RE = re.compile(
    r"frame=(\d+)/(\d+)\s*\(([\d.]+)%\)\s*;\s*fps=([\d.]+)\s*;\s*elapsed=(\d{2}):(\d{2}):(\d{2})\s*;\s*remaining=(\d{2}):(\d{2}):(\d{2})"
)


@dataclass
class ProgressUpdate:
    frames_processed: int
    frames_total: int
    percent: float
    fps: float
    elapsed_seconds: int
    eta_seconds: int


def parse_timecode(h: str, m: str, s: str) -> int:
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse_progress_line(line: str) -> Optional[ProgressUpdate]:
    m = PROGRESS_RE.search(line)
    if not m:
        return None
    fp, ft, pct, fps, eh, em, es, rh, rm, rs = m.groups()
    return ProgressUpdate(
        frames_processed=int(fp),
        frames_total=int(ft),
        percent=float(pct),
        fps=float(fps),
        elapsed_seconds=parse_timecode(eh, em, es),
        eta_seconds=parse_timecode(rh, rm, rs),
    )


class ProgressStreamParser:
    """Split a byte stream into lines on \\r, \\n, or \\r\\n."""

    def __init__(self):
        self._buf = ""

    def feed(self, chunk: str) -> list[str]:
        self._buf += chunk
        lines: list[str] = []
        # normalize
        parts = re.split(r"\r\n|\r|\n", self._buf)
        # last part may be incomplete
        self._buf = parts[-1]
        for p in parts[:-1]:
            if p.strip():
                lines.append(p)
        # also emit if buf contains a complete progress line with trailing spaces
        return lines

    def flush(self) -> list[str]:
        out = []
        if self._buf.strip():
            out.append(self._buf)
        self._buf = ""
        return out
