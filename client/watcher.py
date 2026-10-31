"""Input directory scanning and state tracking."""

from __future__ import annotations

import json
import os
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}


def scan_input(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []
    return sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {"completed": [], "failed": [], "in_progress": None}
    try:
        return json.loads(state_path.read_text())
    except Exception:
        return {"completed": [], "failed": [], "in_progress": None}


def save_state(state_path: Path, state: dict) -> None:
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, state_path)


def filter_completed(files: list[Path], state: dict) -> list[Path]:
    completed = set(state.get("completed", []))
    return [f for f in files if f.name not in completed]
