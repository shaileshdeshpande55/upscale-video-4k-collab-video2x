"""Upscale profiles and command builders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import Settings


@dataclass
class ProfileSpec:
    name: str
    description: str
    # video2x args
    processor: str  # realesrgan | libplacebo
    scale: Optional[int]  # for realesrgan
    model: Optional[str]
    # libplacebo target (only for fast)
    width: Optional[int] = None
    height: Optional[int] = None
    shader: Optional[str] = None
    # whether a second ffmpeg resize pass is needed
    needs_resize: bool = False
    intermediate_scale: Optional[int] = None  # e.g. 4


PROFILES: dict[str, ProfileSpec] = {
    "quality": ProfileSpec(
        name="quality",
        description="Real-ESRGAN x4 (best quality for live action) + ffmpeg downscale to 4K",
        processor="realesrgan",
        scale=4,
        model="realesrgan-plus",
        needs_resize=True,
        intermediate_scale=4,
    ),
    "anime": ProfileSpec(
        name="anime",
        description="realesr-animevideov3 x3 (exact 4K, one pass, anime-tuned)",
        processor="realesrgan",
        scale=3,
        model="realesr-animevideov3",
        needs_resize=False,
    ),
    "fast": ProfileSpec(
        name="fast",
        description="libplacebo Anime4K (exact 4K canvas, fastest)",
        processor="libplacebo",
        scale=None,
        model=None,
        width=3840,
        height=2160,
        shader="anime4k-v4-a+a",
        needs_resize=False,
    ),
}


def build_video2x_command(
    profile_name: str,
    input_path: Path,
    output_path: Path,
    settings: Settings,
    codec: str = "libx264",
    crf: int = 18,
    model_override: Optional[str] = None,
) -> list[str]:
    spec = PROFILES[profile_name]
    cmd = [settings.video2x_bin, "-i", str(input_path), "-o", str(output_path)]

    if spec.processor == "realesrgan":
        model = model_override or spec.model
        cmd += ["-p", "realesrgan", "-s", str(spec.scale), "--realesrgan-model", model]
    else:
        cmd += ["-p", "libplacebo", "-w", str(spec.width), "-h", str(spec.height),
                "--libplacebo-shader", spec.shader]

    cmd += ["-c", codec]
    if codec.startswith("libx264"):
        cmd += ["-e", "preset=veryfast", "-e", f"crf={crf}"]
    elif codec.startswith("libx265"):
        cmd += ["-e", "preset=fast", "-e", f"crf={crf}"]

    return cmd


def build_resize_command(
    input_path: Path,
    output_path: Path,
    settings: Settings,
    crf: int = 18,
    codec: str = "libx264",
) -> list[str]:
    """Aspect-ratio-preserving downscale to a max 3840x2160 canvas."""
    vf = "scale='min(3840,iw)':'min(2160,ih)':force_original_aspect_ratio=decrease"
    return [
        settings.ffmpeg_bin, "-y", "-i", str(input_path),
        "-vf", vf,
        "-c:v", codec, "-preset", "veryfast", "-crf", str(crf),
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
