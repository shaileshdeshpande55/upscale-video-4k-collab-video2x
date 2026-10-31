"""Video2X subprocess runner with progress parsing."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.progress import ProgressStreamParser, parse_progress_line


@dataclass
class RunResult:
    returncode: int
    stderr_tail: str = ""
    cancelled: bool = False


def run_video2x(
    cmd: list[str],
    on_progress: Optional[Callable[[object], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    timeout_s: int = 0,
) -> RunResult:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    parser = ProgressStreamParser()
    stderr_lines: list[str] = []
    cancelled = False

    def reader():
        nonlocal cancelled
        assert proc.stdout is not None
        for chunk in iter(lambda: proc.stdout.read(4096), ""):
            if not chunk:
                break
            for line in parser.feed(chunk):
                stderr_lines.append(line)
                upd = parse_progress_line(line)
                if upd is not None and on_progress is not None:
                    on_progress(upd)
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                try:
                    proc.stdin.write("q\n")
                    proc.stdin.flush()
                except Exception:
                    pass
                break
        proc.stdout.close()

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    try:
        if timeout_s and timeout_s > 0:
            proc.wait(timeout=timeout_s)
        else:
            proc.wait()
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    t.join(timeout=5)
    if proc.returncode is None:
        proc.kill()
        proc.wait()

    if cancelled and proc.returncode is None:
        proc.kill()

    tail = "\n".join(stderr_lines[-40:])
    return RunResult(returncode=proc.returncode if proc.returncode is not None else -1,
                    stderr_tail=tail, cancelled=cancelled)
