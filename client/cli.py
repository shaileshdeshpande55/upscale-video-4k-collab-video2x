"""CLI entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

from config import Settings, parse_args, prompt_if_missing
from watcher import scan_input, filter_completed
from api import ColabClient
from pipeline import Pipeline
from ui import PipelineUI


async def async_main(settings: Settings) -> None:
    settings = prompt_if_missing(settings)
    if not settings.url or not settings.token:
        print("URL and token are required.")
        return

    client = ColabClient(settings.url, settings.token)
    try:
        await client.health()
    except Exception as e:
        print(f"Cannot reach backend: {e}")
        await client.close()
        return

    sysinfo = await client.system()
    print(f"Connected. GPU: {sysinfo.get('gpu', 'unknown')}")

    settings.input_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.failed_dir.mkdir(parents=True, exist_ok=True)

    ui = PipelineUI()
    ui.start()

    try:
        while True:
            files = scan_input(settings.input_dir)
            state_path = settings.state_file
            from watcher import load_state
            state = load_state(state_path)
            files = filter_completed(files, state)
            if not files:
                print("No new videos in input/. Drop files and press Enter, or Ctrl+C to exit.")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    break
                continue

            pipeline = Pipeline(
                client=client,
                input_dir=settings.input_dir,
                output_dir=settings.output_dir,
                failed_dir=settings.failed_dir,
                state_path=state_path,
                profile=settings.profile,
                codec=settings.codec,
                crf=settings.crf,
                poll_interval=settings.poll_interval,
                max_retries=settings.max_retries,
                ui=ui,
            )
            summary = await pipeline.run(files)
            ui.show_summary(summary)
            print("Batch done. Drop more files and press Enter, or Ctrl+C to exit.")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                break
    finally:
        ui.stop()
        await client.close()


def main():
    settings = parse_args()
    asyncio.run(async_main(settings))


if __name__ == "__main__":
    main()
