"""Colab launcher: starts uvicorn + ngrok tunnel."""

from __future__ import annotations

import os
import sys
import time
import threading

from app.config import load_settings
from app.main import create_app


def main():
    settings = load_settings()
    token = settings.ngrok_token
    if not token:
        print("ERROR: NGROK_TOKEN not set. Add it to Colab Secrets.", file=sys.stderr)
        sys.exit(1)
    if not settings.api_token:
        print("ERROR: API_TOKEN not set. Add it to Colab Secrets.", file=sys.stderr)
        sys.exit(1)

    import uvicorn
    from pyngrok import ngrok

    from app.db import JobStore
    from app.jobs import JobManager

    def factory(s):
        return JobManager(JobStore(s.data_dir / "jobs.db"), s)

    application = create_app(settings, job_manager_factory=factory)

    import os as _os
    import glob
    import subprocess

    # clear any stale ngrok config
    ngrok_cfg = _os.path.expanduser("~/.config/ngrok/ngrok.yml")
    if _os.path.exists(ngrok_cfg):
        _os.remove(ngrok_cfg)

    # vulkan ICD setup - use EGL library
    import json
    egl_lib = "/usr/lib64-nvidia/libEGL_nvidia.so.0"
    assert _os.path.exists(egl_lib), "NVIDIA EGL library missing"
    icd_path = "/usr/share/vulkan/icd.d/nvidia_icd.json"
    _os.makedirs("/usr/share/vulkan/icd.d", exist_ok=True)
    with open(icd_path, "w") as f:
        json.dump({
            "file_format_version": "1.0.0",
            "ICD": {
                "library_path": egl_lib,
                "api_version": "1.3.242"
            }
        }, f, indent=2)
    _os.environ["LD_LIBRARY_PATH"] = "/usr/lib64-nvidia:" + _os.environ.get("LD_LIBRARY_PATH", "")
    _os.environ["VK_ICD_FILENAMES"] = icd_path

    r = subprocess.run(["video2x", "--list-devices"], capture_output=True, text=True)
    print("Vulkan:", r.stdout.strip()[:200] if r.stdout.strip() else r.stderr.strip()[:200])

    ngrok.set_auth_token(token)

    # start uvicorn in a thread
    config = uvicorn.Config(application, host="0.0.0.0", port=settings.port, log_level="info")
    server = uvicorn.Server(config)

    def run_server():
        server.run()

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    # wait for server
    time.sleep(3)

    public_url = ngrok.connect(settings.port, "http").public_url
    print("=" * 60)
    print(f"Backend URL : {public_url}")
    print(f"API Token   : {settings.api_token}")
    print("=" * 60)
    print("Paste both into the Windows CLI client.")
    print("Keep this cell running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        ngrok.kill()
        server.should_exit = True
        t.join(timeout=5)


if __name__ == "__main__":
    main()
