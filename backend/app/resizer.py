"""FFmpeg resize step for the quality profile."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from app.progress import parse_timecode


@dataclass
class RunResult:
    returncode: int
    stderr_tail: str = ""
    cancelled: bool = False


def run_resize(
    cmd: list[str],
    duration_s: float,
    on_progress: Optional[Callable[[float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> RunResult:
    # Inject -progress pipe:1 -nostats before output if not present
    if "-progress" not in cmd:
        # find output path (last arg) and insert before it
        out = cmd[-1]
        cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats", out]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    cancelled = False
    current_ms = 0

    def reader():
        nonlocal cancelled, current_ms
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.strip())
            if "=" in line:
                key, _, val = line.strip().partition("=")
                if key == "out_time_ms":
                    try:
                        current_ms = int(val)
                        if duration_s > 0 and on_progress is not None:
                            pct = min(100.0, current_ms / 1e6 / duration_s * 100.0)
                            on_progress(pct)
                    except ValueError:
                        pass
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                try:
                    proc.terminate()
                except Exception:
                    pass
                break
        proc.stdout.close()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    proc.wait()
    t.join(timeout=5)
    if proc.returncode is None:
        proc.kill()
        proc.wait()

    tail = "\n".join(lines[-20:])
    return RunResult(returncode=proc.returncode if proc.returncode is not None else -1,
                    stderr_tail=tail, cancelled=cancelled)
