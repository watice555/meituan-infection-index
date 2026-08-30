#!/usr/bin/env python3
"""Extract a minimal private request template from a decrypted Proxyman HAR."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "data" / "request_template.json"
ENDPOINT_HOST = "yiyao-h5.meituan.com"
ENDPOINT_PATH = "/api/v1/health/marketingc/gateway/delivery/hawkeye/index"
SAFE_HEADER_NAMES = {
    "accept",
    "accept-language",
    "content-type",
    "origin",
    "referer",
    "user-agent",
    "dj-token",
}
SENSITIVE_BODY_KEYS = {
    "token",
    "userid",
    "userId",
    "address",
    "uuid",
    "wmUuidDeregistration",
    "wm_visitid",
    "wm_logintoken",
    "wmUserIdDeregistration",
    "wm_uuid",
    "wm_did",
    "msid",
    "utm_content",
}


def find_request(har: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request") or {}
        parsed = urlsplit(str(request.get("url", "")))
        if (
            request.get("method") == "POST"
            and parsed.scheme == "https"
            and parsed.netloc == ENDPOINT_HOST
            and parsed.path == ENDPOINT_PATH
        ):
            return request, entry.get("startedDateTime")
    raise ValueError("HAR 中没有找到已解密的美团传染病指数 POST 请求")


def build_template(request: dict[str, Any], captured_at: str | None) -> dict[str, Any]:
    headers = {
        str(header.get("name", "")).lower(): str(header.get("value", ""))
        for header in request.get("headers", [])
        if str(header.get("name", "")).lower() in SAFE_HEADER_NAMES
    }
    if not headers.get("dj-token"):
        raise ValueError("目标请求缺少 dj-token；请确认该域已在 Proxyman 中启用 SSL 解密")

    raw_body = (request.get("postData") or {}).get("text")
    body = json.loads(raw_body)
    if not isinstance(body, dict):
        raise ValueError("目标请求体不是 JSON 对象")
    for key in SENSITIVE_BODY_KEYS:
        if key in body:
            body[key] = ""
    body["req_time"] = 0

    return {
        "version": 1,
        "endpoint": f"https://{ENDPOINT_HOST}{ENDPOINT_PATH}",
        "headers": headers,
        "body": body,
        "source_captured_at": captured_at,
    }


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    har = json.loads(args.har.read_text(encoding="utf-8"))
    request, captured_at = find_request(har)
    template = build_template(request, captured_at)
    write_private_json(args.output, template)
    print(args.output)
    print("已仅保留 dj-token 与非唯一业务参数；Cookie、登录态、地址和设备标识均未写入模板。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
