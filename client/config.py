"""Client configuration."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    url: str = ""
    token: str = ""
    input_dir: Path = field(default_factory=lambda: Path(os.environ.get("V2X_INPUT_DIR", "./input")))
    output_dir: Path = field(default_factory=lambda: Path(os.environ.get("V2X_OUTPUT_DIR", "./output")))
    failed_dir: Path = field(default_factory=lambda: Path(os.environ.get("V2X_FAILED_DIR", "./failed")))
    state_file: Path = field(default_factory=lambda: Path(os.environ.get("V2X_STATE_FILE", "./state.json")))
    profile: str = field(default_factory=lambda: os.environ.get("V2X_PROFILE", "quality"))
    codec: str = field(default_factory=lambda: os.environ.get("V2X_CODEC", "libx264"))
    crf: int = field(default_factory=lambda: int(os.environ.get("V2X_CRF", "18")))
    poll_interval: float = field(default_factory=lambda: float(os.environ.get("V2X_POLL_INTERVAL", "1.0")))
    max_retries: int = field(default_factory=lambda: int(os.environ.get("V2X_MAX_RETRIES", "3")))
    concurrent_uploads: int = field(default_factory=lambda: int(os.environ.get("V2X_CONCURRENT_UPLOADS", "1")))


def parse_args(argv=None) -> Settings:
    s = Settings()
    parser = argparse.ArgumentParser(description="Video2X CLI client")
    parser.add_argument("--url", default=s.url or os.environ.get("V2X_URL", ""))
    parser.add_argument("--token", default=s.token or os.environ.get("V2X_TOKEN", ""))
    parser.add_argument("--input", default=str(s.input_dir))
    parser.add_argument("--output", default=str(s.output_dir))
    parser.add_argument("--failed", default=str(s.failed_dir))
    parser.add_argument("--profile", default=s.profile, choices=["quality", "anime", "fast"])
    parser.add_argument("--codec", default=s.codec)
    parser.add_argument("--crf", type=int, default=s.crf)
    parser.add_argument("--poll-interval", type=float, default=s.poll_interval)
    parser.add_argument("--max-retries", type=int, default=s.max_retries)
    args = parser.parse_args(argv)
    s.url = args.url
    s.token = args.token
    s.input_dir = Path(args.input)
    s.output_dir = Path(args.output)
    s.failed_dir = Path(args.failed)
    s.profile = args.profile
    s.codec = args.codec
    s.crf = args.crf
    s.poll_interval = args.poll_interval
    s.max_retries = args.max_retries
    return s


def prompt_if_missing(s: Settings) -> Settings:
    if not s.url:
        s.url = input("Backend URL (ngrok): ").strip()
    if not s.token:
        import getpass
        s.token = getpass.getpass("API token: ").strip()
    return s
