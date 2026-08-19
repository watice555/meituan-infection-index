#!/usr/bin/env python3
"""Fetch and merge public Meituan infection-index series for the static site."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "config" / "request_template.json"
DEFAULT_OUTPUT = ROOT / "data" / "indexes.json"
ENDPOINT = "https://yiyao-h5.meituan.com/api/v1/health/marketingc/gateway/delivery/hawkeye/index"
CITIES = (
    ("杭州市", "330100"),
    ("上海市", "310100"),
    ("北京市", "110100"),
    ("深圳市", "440300"),
    ("广州市", "440100"),
)


class FetchError(RuntimeError):
    """Raised when collection or response validation fails."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_date(value: Any) -> str:
    raw = str(value)
    for date_format in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return dt.datetime.strptime(raw, date_format).date().isoformat()
        except ValueError:
            continue
    raise FetchError(f"无法识别指数日期：{raw!r}")


def load_template(path: Path, token: str) -> dict[str, Any]:
    template = json.loads(path.read_text(encoding="utf-8"))
    if template.get("version") != 1 or template.get("endpoint") != ENDPOINT:
        raise FetchError("请求模板版本或目标接口无效")
    if not token.strip():
        raise FetchError("缺少 MEITUAN_DJ_TOKEN")
    headers = template.get("headers")
    body = template.get("body")
    if not isinstance(headers, dict) or not isinstance(body, dict):
        raise FetchError("请求模板缺少 headers 或 body")
    template["headers"] = {**headers, "dj-token": token.strip()}
    return template


def post_index(
    template: dict[str, Any], city_id: str, material_id: str, timeout: float
) -> dict[str, Any]:
    body = copy.deepcopy(template["body"])
    body.update(
        {
            "city_id": int(city_id),
            "scene": 1,
            "materialId": [str(material_id)],
            "req_time": int(time.time() * 1000),
        }
    )
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={str(key): str(value) for key, value in template["headers"].items()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise FetchError(f"美团接口返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"无法连接美团接口：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise FetchError("美团接口返回了非 JSON 内容") from exc

    if not isinstance(payload, dict) or payload.get("code") != 0 or payload.get("success") is not True:
        code = payload.get("code") if isinstance(payload, dict) else None
        message = payload.get("msg") if isinstance(payload, dict) else None
        raise FetchError(f"美团接口拒绝请求（code={code}, msg={message!r}）")
    return payload


def discover_material_ids(payload: dict[str, Any]) -> list[str]:
    module = ((payload.get("data") or {}).get("cityHealthDetailModule") or {})
    discovered: list[str] = []
    for item in module.get("diseaseStatusList") or []:
        material_id = str(item.get("materialId", "")).strip()
        if material_id and material_id not in discovered:
            discovered.append(material_id)
    return discovered


def extract_series(
    payload: dict[str, Any], expected_city: str, city_id: str, material_id: str
) -> dict[str, Any]:
    data = payload.get("data") or {}
    module = data.get("cityHealthDetailModule") or {}
    city = str(data.get("cityName") or module.get("cityName") or "")
    disease = str(data.get("diseaseName") or "")
    disease_id = data.get("diseaseId")
    raw_points = module.get("diseaseSearchIndexList") or []
    if city != expected_city:
        raise FetchError(f"city_id={city_id} 预期 {expected_city}，接口实际返回 {city or '空城市'}")
    if disease_id is None or not disease or not raw_points:
        raise FetchError(f"{expected_city} materialId={material_id} 缺少疾病或曲线数据")

    points: list[list[Any]] = []
    for point in raw_points:
        value = point.get("value") if isinstance(point, dict) else None
        if not isinstance(value, (int, float)):
            raise FetchError(f"{expected_city} {disease} 包含无效曲线点")
        points.append([normalize_date(point.get("date")), float(value)])
    points.sort(key=lambda item: item[0])
    return {
        "city": city,
        "city_id": city_id,
        "disease": disease,
        "disease_id": int(disease_id),
        "material_id": str(material_id),
        "points": points,
    }


def fetch_city(
    template: dict[str, Any], city: str, city_id: str, timeout: float, delay: float
) -> list[dict[str, Any]]:
    seed_ids = template["body"].get("materialId") or []
    if not seed_ids:
        raise FetchError("请求模板缺少种子 materialId")
    seed_id = str(seed_ids[0])
    seed_payload = post_index(template, city_id, seed_id, timeout)
    discovered = discover_material_ids(seed_payload)
    material_ids = [seed_id, *(item for item in discovered if item != seed_id)]
    if len(material_ids) < 5:
        raise FetchError(f"{city} 只发现 {len(material_ids)} 种指数，停止覆盖历史数据")

    series = [extract_series(seed_payload, city, city_id, seed_id)]
    for material_id in material_ids[1:]:
        if delay:
            time.sleep(delay)
        series.append(extract_series(post_index(template, city_id, material_id, timeout), city, city_id, material_id))
    return series


def load_history(path: Path | None) -> dict[tuple[str, int], dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("version") != 1 or not isinstance(document.get("series"), list):
        raise FetchError("历史 JSON 格式无效")
    history: dict[tuple[str, int], dict[str, Any]] = {}
    for item in document["series"]:
        if not isinstance(item, dict):
            raise FetchError("历史 JSON 包含无效 series")
        normalized = {
            "city": str(item["city"]),
            "city_id": str(item["city_id"]),
            "disease": str(item["disease"]),
            "disease_id": int(item["disease_id"]),
            "material_id": str(item["material_id"]),
            "points": [[normalize_date(date), float(value)] for date, value in item["points"]],
        }
        history[(normalized["city_id"], normalized["disease_id"])] = normalized
    return history


def merge_series(
    history: dict[tuple[str, int], dict[str, Any]],
    fresh: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = copy.deepcopy(history)
    for item in fresh:
        key = (item["city_id"], item["disease_id"])
        previous = merged.get(key)
        points = {date: value for date, value in (previous or {}).get("points", [])}
        points.update({date: value for date, value in item["points"]})
        merged[key] = {
            **item,
            "points": [[date, points[date]] for date in sorted(points)],
        }
    return sorted(merged.values(), key=lambda item: (item["city_id"], item["disease_id"]))


def validate_document(document: dict[str, Any], expected_cities: int = 5) -> None:
    series = document.get("series")
    if document.get("version") != 1 or not isinstance(series, list):
        raise FetchError("输出 JSON 缺少 version=1 或 series")
    current_cities = {item.get("city_id") for item in series}
    if len(current_cities) < expected_cities:
        raise FetchError(f"输出 JSON 只有 {len(current_cities)} 个城市")
    current_pairs = {(item.get("city_id"), item.get("disease_id")) for item in series}
    if len(current_pairs) < expected_cities * 5:
        raise FetchError(f"输出 JSON 只有 {len(current_pairs)} 条城市/疾病序列")
    if any(len(item.get("points") or []) < 14 for item in series):
        raise FetchError("至少一条序列少于 14 个数据点")


def write_document(path: Path, document: dict[str, Any]) -> None:
    validate_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def collect(
    template_path: Path,
    token: str,
    history_path: Path | None,
    output_path: Path,
    timeout: float,
    delay: float,
) -> dict[str, Any]:
    template = load_template(template_path, token)
    history = load_history(history_path)
    fresh: list[dict[str, Any]] = []
    for city, city_id in CITIES:
        fresh.extend(fetch_city(template, city, city_id, timeout, delay))
    document = {
        "version": 1,
        "updated_at": utc_now(),
        "source": "美团 App 传染病指数",
        "series": merge_series(history, fresh),
    }
    write_document(output_path, document)
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=0.25)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    document = collect(
        args.template,
        os.environ.get("MEITUAN_DJ_TOKEN", ""),
        args.history,
        args.output,
        args.timeout,
        args.delay,
    )
    print(
        json.dumps(
            {
                "updated_at": document["updated_at"],
                "series": len(document["series"]),
                "points": sum(len(item["points"]) for item in document["series"]),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FetchError, FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc
