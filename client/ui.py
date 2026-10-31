"""Terminal UI for the pipeline."""

from __future__ import annotations

from typing import Optional

try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

    HAS_RICH = True
except Exception:
    HAS_RICH = False


class PipelineUI:
    def __init__(self):
        self._statuses: dict[str, dict] = {}
        self._console = Console() if HAS_RICH else None
        self._live = None

    def start(self):
        if HAS_RICH:
            self._live = Live(self._render(), refresh_per_second=4)
            self._live.start()

    def stop(self):
        if self._live:
            self._live.stop()

    def update(self, filename: str, status: str, progress: float, fps: Optional[float], eta: Optional[str]):
        self._statuses[filename] = {
            "status": status, "progress": progress, "fps": fps, "eta": eta,
        }
        if self._live:
            self._live.update(self._render())

    def _render(self):
        if not HAS_RICH:
            return None
        table = Table(title="Video2X Pipeline")
        table.add_column("File")
        table.add_column("Status")
        table.add_column("Progress")
        table.add_column("FPS")
        table.add_column("ETA")
        for name, info in self._statuses.items():
            table.add_row(
                name,
                info["status"],
                f"{info['progress']:.1f}%",
                f"{info['fps']:.2f}" if info["fps"] else "-",
                str(info["eta"]) if info["eta"] else "-",
            )
        return table

    def show_summary(self, summary):
        msg = f"Done: {summary.completed} completed, {summary.failed} failed"
        if self._console:
            self._console.print(msg)
        else:
            print(msg)
