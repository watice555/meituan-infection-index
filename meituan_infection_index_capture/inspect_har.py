#!/usr/bin/env python3
"""Find date/value series in JSON responses from a Proxyman HAR export."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


DATE_RE = re.compile(r"^20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}(?:[T\s].*)?$")
COMPACT_DATE_RE = re.compile(r"^20\d{6}$")
SHORT_DATE_RE = re.compile(r"^\d{1,2}[-/.]\d{1,2}$")
KEYWORDS = (
    "disease",
    "infection",
    "infectious",
    "epidemic",
    "trend",
    "chart",
    "index",
    "传染",
    "感染",
    "指数",
    "趋势",
    "曲线",
)
DATE_KEYS = ("date", "dates", "day", "days", "time", "times", "x", "xaxis", "label", "labels")
VALUE_KEYS = ("value", "values", "index", "indices", "score", "scores", "y", "yaxis", "count", "counts")


def looks_like_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return bool(DATE_RE.match(stripped) or COMPACT_DATE_RE.match(stripped) or SHORT_DATE_RE.match(stripped))


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z]", "", str(key).lower())


def key_matches(key: Any, choices: tuple[str, ...]) -> bool:
    normalized = normalized_key(key)
    return any(normalized == choice or normalized.endswith(choice) for choice in choices)


def array_pair_candidates(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    date_arrays = [
        (key, child)
        for key, child in value.items()
        if key_matches(key, DATE_KEYS)
        and isinstance(child, list)
        and len(child) >= 2
        and all(looks_like_date(item) for item in child)
    ]
    number_arrays = [
        (key, child)
        for key, child in value.items()
        if key_matches(key, VALUE_KEYS)
        and isinstance(child, list)
        and len(child) >= 2
        and all(is_number(item) for item in child)
    ]
    candidates = []
    for date_key, dates in date_arrays:
        for value_key, numbers in number_arrays:
            if len(dates) == len(numbers):
                candidates.append(
                    {
                        "json_path": path,
                        "date_key": str(date_key),
                        "value_key": str(value_key),
                        "points": [
                            {"date": date, "value": number}
                            for date, number in zip(dates, numbers, strict=True)
                        ],
                    }
                )
    return candidates


def row_candidates(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) < 2 or not all(isinstance(item, dict) for item in value):
        return []
    common_keys = set.intersection(*(set(item) for item in value))
    date_keys = [
        key
        for key in common_keys
        if key_matches(key, DATE_KEYS) and all(looks_like_date(item[key]) for item in value)
    ]
    value_keys = [
        key
        for key in common_keys
        if key_matches(key, VALUE_KEYS) and all(is_number(item[key]) for item in value)
    ]
    candidates = []
    for date_key in date_keys:
        for value_key in value_keys:
            candidates.append(
                {
                    "json_path": path,
                    "date_key": str(date_key),
                    "value_key": str(value_key),
                    "points": [
                        {"date": item[date_key], "value": item[value_key]}
                        for item in value
                    ],
                }
            )
    return candidates


def decode_content(content: dict[str, Any]) -> str | None:
    text = content.get("text")
    if not isinstance(text, str):
        return None
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    return text


def inspect_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
    request = entry.get("request") or {}
    response = entry.get("response") or {}
    content = response.get("content") or {}
    text = decode_content(content)
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    url = str(request.get("url", ""))
    parsed_url = urlsplit(url)
    safe_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", ""))
    keyword_text = f"{safe_url}\n{text[:20000]}".lower()
    matched_keywords = sorted({word for word in KEYWORDS if word in keyword_text})
    results = []
    seen: set[tuple[str, str, str]] = set()
    for path, value in walk(payload):
        for candidate in array_pair_candidates(value, path) + row_candidates(value, path):
            identity = (candidate["json_path"], candidate["date_key"], candidate["value_key"])
            if identity in seen:
                continue
            seen.add(identity)
            point_count = len(candidate["points"])
            candidate.update(
                {
                    "score": point_count + 5 * len(matched_keywords),
                    "matched_keywords": matched_keywords,
                    "method": request.get("method"),
                    "url": safe_url,
                    "status": response.get("status"),
                }
            )
            results.append(candidate)
    return results


def inspect_har(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("log", {}).get("entries", [])
    candidates = [candidate for entry in entries for candidate in inspect_entry(entry)]
    return sorted(candidates, key=lambda item: (-item["score"], item["url"], item["json_path"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    candidates = inspect_har(args.har)
    output = json.dumps({"candidate_count": len(candidates), "candidates": candidates}, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
        print(args.report)
    else:
        print(output)
    return 0 if candidates else 2


if __name__ == "__main__":
    raise SystemExit(main())
