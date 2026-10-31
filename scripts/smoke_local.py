"""Local smoke test using the FastAPI app with a fake video2x binary."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import JobStore
from app.jobs import JobManager
from app.main import create_app
from app.models import VideoInfo


def main():
    root = Path(tempfile.mkdtemp())
    try:
        data = root / "data"
        data.mkdir()
        settings = Settings(data_dir=data, api_token="testtoken", allow_insecure=False)

        fake = root / "fake_v2x.py"
        fake.write_text(
            "import sys, time\n"
            "out = sys.argv[sys.argv.index('-o')+1]\n"
            "for i in range(1, 6):\n"
            "    print(f'frame={i}/5 ({i*20}.00%); fps=2.00; elapsed=00:00:0{i}; remaining=00:00:0{5-i}', flush=True)\n"
            "    time.sleep(0.1)\n"
            "open(out,'wb').write(b'fakevideo')\n"
        )
        if os.name == "nt":
            wrapper = root / "wrapper.bat"
            wrapper.write_text(f'@echo off\n"{sys.executable}" "{fake}" %*\n')
        else:
            wrapper = root / "wrapper.sh"
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n')
            wrapper.chmod(0o755)
        settings.video2x_bin = str(wrapper)

        def fake_probe(path, bin):
            return VideoInfo(width=1280, height=720, duration=5.0, size=path.stat().st_size)

        def factory(s):
            return JobManager(JobStore(s.data_dir / "jobs.db"), s, probe=fake_probe)

        app = create_app(settings, job_manager_factory=factory)
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer testtoken"}
            inp = root / "clip.mp4"
            inp.write_bytes(b"fakeinput" * 100)
            with inp.open("rb") as f:
                r = client.post("/api/jobs", files={"file": ("clip.mp4", f, "video/mp4")},
                                data={"profile": "anime"}, headers=headers)
            print("create:", r.status_code)
            assert r.status_code == 201
            job_id = r.json()["id"]

            for _ in range(50):
                r = client.get(f"/api/jobs/{job_id}", headers=headers)
                j = r.json()
                print(f"  status={j['status']} progress={j['progress']:.1f}")
                if j["status"] in ("completed", "failed", "canceled"):
                    break
                time.sleep(0.5)

            assert j["status"] == "completed", j
            r = client.get(f"/api/jobs/{job_id}/download", headers=headers)
            assert r.status_code == 200
            print("download ok, size:", len(r.content))
            print("SMOKE PASSED")
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
