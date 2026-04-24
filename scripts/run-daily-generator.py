#!/usr/bin/env python3

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def load_env_file(file_path: Path) -> None:
    if not file_path.exists():
        return

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def seconds_until_next_midnight(timezone_name: str) -> float:
    now = now_in_timezone(timezone_name)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max((next_midnight - now).total_seconds(), 1)


def run_generation_for_date(target_date: str) -> int:
    cmd = ["python3", "scripts/generate-daily-puzzle.py", f"--date={target_date}"]
    process = subprocess.run(cmd, cwd=Path.cwd(), env=os.environ.copy())
    return process.returncode


def main() -> None:
    load_env_file(Path(".env"))
    timezone_name = os.environ.get("PIXORDLE_TIMEZONE", "America/Chicago")

    print(f"Daily generator daemon running in timezone: {timezone_name}")
    while True:
        wait_seconds = seconds_until_next_midnight(timezone_name)
        run_at = now_in_timezone(timezone_name) + timedelta(seconds=wait_seconds)
        print(f"Next generation scheduled at: {run_at.isoformat()}")
        time.sleep(wait_seconds)

        date_key = now_in_timezone(timezone_name).strftime("%Y-%m-%d")
        print(f"Generating puzzle for {date_key}...")
        exit_code = run_generation_for_date(date_key)
        if exit_code == 0:
            print("Generation succeeded")
        else:
            print(f"Generation failed with exit code {exit_code}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped daily generator daemon")
