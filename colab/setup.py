"""Colab setup: install system deps, Video2X AppImage, repo, build."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO2X_URL = "https://github.com/k4yt3x/video2x/releases/download/6.4.0/Video2X-x86_64.AppImage"
VIDEO2X_VERSION = "6.4.0"


def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, check=False)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed ({r.returncode}): {' '.join(cmd)}")
    return r


def check_gpu():
    r = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], check=False)
    if r.returncode != 0:
        raise RuntimeError("No GPU detected. Set runtime to GPU in Colab.")
    print("GPU OK")


def install_system_deps():
    run(["apt-get", "-qq", "update"])
    run(["apt-get", "-qq", "install", "-y", "libvulkan1", "vulkan-tools", "libfuse2", "ffmpeg"])


def install_video2x(dest: Path = Path("/content")):
    appimage = dest / "Video2X.AppImage"
    if not appimage.exists():
        run(["wget", "-q", VIDEO2X_URL, "-O", str(appimage)])
    appimage.chmod(0o755)
    # extract
    squash = dest / "squashfs-root"
    if not squash.exists():
        run(["bash", "-c", f"cd {dest} && ./Video2X.AppImage --appimage-extract"])
    # symlink to AppRun (original approach)
    apprun = squash / "AppRun"
    if apprun.exists():
        target = Path("/usr/local/bin/video2x")
        if target.exists() or target.is_symlink():
            target.unlink()
        run(["ln", "-sf", str(apprun), str(target)])
        print("Symlinked video2x -> AppRun")
    # verify
    r = run(["video2x", "--version"], check=False)
    if r.returncode != 0:
        raise RuntimeError("Video2X failed to start. Check Vulkan setup.")

    # vulkan ICD setup - create wrapper script that sets env vars
    import glob
    os.makedirs("/usr/share/vulkan/icd.d", exist_ok=True)
    glx_libs = glob.glob("/usr/lib/x86_64-linux-gnu/libGLX_nvidia*.so*")
    print("GLX libs:", glx_libs)
    if glx_libs:
        versioned = sorted(glx_libs)[-1]
        unversioned = "/usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0"
        if not os.path.exists(unversioned):
            os.symlink(versioned, unversioned)
            print(f"Created symlink {unversioned} -> {versioned}")
    icd = Path("/usr/share/vulkan/icd.d/nvidia_icd.json")
    icd.write_text('{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3.242"}}')

    # create wrapper script instead of direct symlink to AppRun
    wrapper = Path("/usr/local/bin/video2x")
    actual = "/content/squashfs-root/usr/bin/video2x"
    wrapper.write_text(f'''#!/bin/bash
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export LD_LIBRARY_PATH=/content/squashfs-root/usr/lib:/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
exec "{actual}" "$@"
''')
    wrapper.chmod(0o755)
    print("Created video2x wrapper")

    r2 = subprocess.run(["video2x", "--list-devices"], capture_output=True, text=True)
    print("Vulkan:", r2.stdout.strip()[:200] if r2.stdout.strip() else r2.stderr.strip()[:200])


def clone_repo(repo_url: str, dest: Path = Path("/content/app")):
    # if stale (missing backend), force re-clone
    if dest.exists() and not (dest / "backend" / "requirements.txt").exists():
        print("Stale repo detected, re-cloning...")
        import shutil
        shutil.rmtree(dest, ignore_errors=True)
    if not dest.exists():
        run(["git", "clone", repo_url, str(dest)])
    else:
        run(["git", "-C", str(dest), "fetch", "--all"], check=False)
        run(["git", "-C", str(dest), "reset", "--hard", "origin/main"], check=False)
        print(f"Repo updated at {dest}")


def install_python_deps(repo_dir: Path):
    run([sys.executable, "-m", "pip", "install", "-q", "-r", str(repo_dir / "backend" / "requirements.txt")])


def build_frontend(repo_dir: Path):
    frontend = repo_dir / "frontend"
    if frontend.exists() and (frontend / "package.json").exists():
        run(["bash", "-c", f"cd {frontend} && npm ci && npm run build"])
        dist = frontend / "dist"
        static = repo_dir / "backend" / "app" / "static"
        if dist.exists():
            static.mkdir(parents=True, exist_ok=True)
            run(["cp", "-r", f"{dist}/.", str(static)])
    else:
        print("No frontend directory; skipping build.")


def setup(repo_url: str):
    check_gpu()
    install_system_deps()
    install_video2x()
    clone_repo(repo_url)
    repo_dir = Path("/content/app")
    install_python_deps(repo_dir)
    build_frontend(repo_dir)
    # create data dirs
    Path("/content/video2x").mkdir(parents=True, exist_ok=True)
    Path("/content/video2x/jobs").mkdir(parents=True, exist_ok=True)
    print("Setup complete.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python setup.py <REPO_URL>")
        sys.exit(1)
    setup(sys.argv[1])
