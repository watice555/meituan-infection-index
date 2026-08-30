#!/usr/bin/env python3
"""Small, secret-safe wrapper around Proxyman's bundled CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys


PROXYMAN_CLI = Path("/Applications/Proxyman.app/Contents/MacOS/proxyman-cli")
BASE_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = BASE_DIR / "captures"


def run_cli(*arguments: str, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    if not PROXYMAN_CLI.is_file():
        raise RuntimeError(f"Proxyman CLI 不存在：{PROXYMAN_CLI}")
    return subprocess.run(
        [str(PROXYMAN_CLI), *arguments],
        check=True,
        capture_output=capture_output,
        text=True,
    )


def status() -> int:
    result = run_cli("proxy-host")
    payload = json.loads(result.stdout)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def clear() -> int:
    run_cli("clear-session", capture_output=False)
    print("已清空当前 Proxyman 会话。")
    return 0


def export() -> int:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    output_path = CAPTURE_DIR / f"meituan_{timestamp}.har"
    run_cli("export-log", "--format", "har", "--output", str(output_path))
    print(output_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "clear", "export"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return {"status": status, "clear": clear, "export": export}[args.command]()
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
