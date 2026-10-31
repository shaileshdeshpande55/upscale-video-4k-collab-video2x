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

    # vulkan ICD: find nvidia lib and create working ICD
    icd_dir = _os.path.join("/usr/share/vulkan/icd.d")
    _os.makedirs(icd_dir, exist_ok=True)
    icd_path = _os.path.join(icd_dir, "nvidia_icd.json")

    # find nvidia vulkan libraries
    candidates = []
    for pattern in ["/usr/lib/x86_64-linux-gnu/libGLX_nvidia*.so*", "/usr/lib/x86_64-linux-gnu/libnvidia-glcore*.so*"]:
        candidates.extend(glob.glob(pattern))
    # also check /usr/lib
    for pattern in ["/usr/lib/libGLX_nvidia*.so*", "/usr/lib/libnvidia-glcore*.so*"]:
        candidates.extend(glob.glob(pattern))

    if not candidates:
        # maybe in squashfs or driver dir
        candidates = ["libGLX_nvidia.so.0"]

    print("Vulkan candidates:", candidates)

    working_icd = None
    for lib in candidates:
        libname = _os.path.basename(lib) if "/" in lib else lib
        # try absolute path first
        for path_val in [lib, libname]:
            icd_content = f'{{"file_format_version":"1.0.0","ICD":{{"library_path":"{path_val}","api_version":"1.3.242"}}}}'
            with open(icd_path, "w") as f:
                f.write(icd_content)
            _os.environ["VK_ICD_FILENAMES"] = icd_path
            r = subprocess.run(["video2x", "--list-devices"], capture_output=True, text=True)
            if "NVIDIA" in r.stdout:
                working_icd = path_val
                print(f"Vulkan OK with {path_val}")
                break
        if working_icd:
            break

    if not working_icd:
        # last resort: try all libs in the nvidia driver dir
        print("Vulkan not working. Trying broader search...")
        all_libs = glob.glob("/usr/lib/x86_64-linux-gnu/lib*nvidia*.so*") + glob.glob("/usr/lib/x86_64-linux-gnu/lib*GLX*.so*")
        for lib in all_libs[:20]:
            libname = _os.path.basename(lib)
            icd_content = f'{{"file_format_version":"1.0.0","ICD":{{"library_path":"{lib}","api_version":"1.3.242"}}}}'
            with open(icd_path, "w") as f:
                f.write(icd_content)
            _os.environ["VK_ICD_FILENAMES"] = icd_path
            r = subprocess.run(["video2x", "--list-devices"], capture_output=True, text=True)
            if "NVIDIA" in r.stdout:
                working_icd = lib
                print(f"Vulkan OK with {lib}")
                break

    if working_icd:
        print(f"Using ICD: {working_icd}")
    else:
        print("WARNING: Vulkan GPU not detected. Video2X will fail.")
        # print diagnostics
        r = subprocess.run(["video2x", "--list-devices"], capture_output=True, text=True)
        print("stdout:", r.stdout[:500])
        print("stderr:", r.stderr[:500])

    # ensure LD_LIBRARY_PATH includes squashfs and system libs
    ld_path = _os.environ.get("LD_LIBRARY_PATH", "")
    extra = "/content/squashfs-root/usr/lib:/usr/lib/x86_64-linux-gnu"
    if extra not in ld_path:
        _os.environ["LD_LIBRARY_PATH"] = extra + (":" + ld_path if ld_path else "")

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
