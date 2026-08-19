#!/usr/bin/env python3
"""Restore the previously published city shards before a new collection run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time
from typing import Any
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "https://watice555.github.io/meituan-infection-index/data/"
CITY_FILE = re.compile(r"cities/[0-9]{6}\.json\Z")


class RestoreError(RuntimeError):
    """Raised when the published history cannot be restored safely."""


def fetch_json(url: str, attempts: int = 3, allow_missing: bool = False) -> dict[str, Any] | None:
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_missing:
                return None
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt + 1 == attempts:
                raise RestoreError(f"恢复历史失败：{url} 返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 == attempts:
                raise RestoreError(f"恢复历史失败：无法访问 {url}") from exc
        except json.JSONDecodeError as exc:
            raise RestoreError(f"恢复历史失败：{url} 不是有效 JSON") from exc
        time.sleep(2**attempt)
    raise RestoreError(f"恢复历史失败：{url}")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def restore(base_url: str, output_dir: Path) -> str:
    base_url = base_url.rstrip("/") + "/"
    manifest = fetch_json(base_url + "manifest.json", allow_missing=True)
    if manifest is None:
        legacy = fetch_json(base_url + "indexes.json", allow_missing=True)
        if legacy is None:
            return "none"
        if legacy.get("version") != 1 or not isinstance(legacy.get("series"), list):
            raise RestoreError("已发布的 indexes.json 格式无效")
        write_json(output_dir / "indexes.json", legacy)
        return "legacy"

    if manifest.get("version") != 2 or not isinstance(manifest.get("cities"), list):
        raise RestoreError("已发布的 manifest.json 格式无效")
    city_entries = manifest["cities"]
    if not city_entries:
        raise RestoreError("已发布的 manifest.json 没有城市")
    for entry in city_entries:
        relative = str(entry.get("file", ""))
        city_id = str(entry.get("city_id", ""))
        if not CITY_FILE.fullmatch(relative) or relative != f"cities/{city_id}.json":
            raise RestoreError("已发布的 manifest.json 包含无效城市文件路径")
        document = fetch_json(base_url + relative)
        if (
            document is None
            or document.get("version") != 1
            or str(document.get("city_id")) != city_id
            or not isinstance(document.get("series"), list)
        ):
            raise RestoreError(f"已发布的 {relative} 格式无效")
        write_json(output_dir / relative, document)
    write_json(output_dir / "manifest.json", manifest)
    return "sharded"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    restored = restore(args.base_url, args.output)
    print(json.dumps({"history": restored, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RestoreError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"错误：{exc}") from exc
