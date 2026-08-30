#!/usr/bin/env python3
"""Fetch, merge, and shard public Meituan infection-index series by city."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import socket
from pathlib import Path
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "config" / "request_template.json"
DEFAULT_OUTPUT_DIR = ROOT / "data"
ENDPOINT = "https://yiyao-h5.meituan.com/api/v1/health/marketingc/gateway/delivery/hawkeye/index"
CITIES = (
    ("杭州市", "330100"),
    ("上海市", "310100"),
    ("北京市", "110100"),
    ("深圳市", "440300"),
    ("广州市", "440100"),
    ("重庆市", "500100"),
    ("长沙市", "430100"),
    ("成都市", "510100"),
    ("长春市", "220100"),
    ("常州市", "320400"),
    ("大连市", "210200"),
    ("东莞市", "441900"),
    ("福州市", "350100"),
    ("佛山市", "440600"),
    ("贵阳市", "520100"),
    ("合肥市", "340100"),
    ("惠州市", "441300"),
    ("呼和浩特市", "150100"),
    ("哈尔滨市", "230100"),
    ("吉林市", "220200"),
    ("济南市", "370100"),
    ("金华市", "330700"),
    ("江门市", "440700"),
    ("昆明市", "530100"),
    ("廊坊市", "131000"),
    ("洛阳市", "410300"),
    ("兰州市", "620100"),
    ("临沂市", "371300"),
    ("南宁市", "450100"),
    ("宁波市", "330200"),
    ("南京市", "320100"),
    ("青岛市", "370200"),
    ("泉州市", "350500"),
    ("汕头市", "440500"),
    ("石家庄市", "130100"),
    ("沈阳市", "210100"),
    ("绍兴市", "330600"),
    ("苏州市", "320500"),
    ("唐山市", "130200"),
    ("天津市", "120100"),
    ("太原市", "140100"),
    ("台州市", "331000"),
    ("武汉市", "420100"),
    ("潍坊市", "370700"),
    ("温州市", "330300"),
    ("无锡市", "320200"),
    ("芜湖市", "340200"),
    ("乌鲁木齐市", "650100"),
    ("徐州市", "320300"),
    ("西安市", "610100"),
    ("厦门市", "350200"),
    ("烟台市", "370600"),
    ("银川市", "640100"),
    ("中山市", "442000"),
    ("珠海市", "440400"),
    ("郑州市", "410100"),
)
MATERIAL_IDS = ("16426", "16427", "16448", "16441", "19625")


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


def load_template(path: Path) -> dict[str, Any]:
    template = json.loads(path.read_text(encoding="utf-8"))
    if template.get("version") != 1 or template.get("endpoint") != ENDPOINT:
        raise FetchError("请求模板版本或目标接口无效")
    headers = template.get("headers")
    body = template.get("body")
    if not isinstance(headers, dict) or not isinstance(body, dict):
        raise FetchError("请求模板缺少 headers 或 body")
    template["headers"] = {
        str(key): value
        for key, value in headers.items()
        if str(key).lower() != "dj-token"
    }
    return template


def post_index(
    template: dict[str, Any],
    city_id: str,
    material_id: str,
    timeout: float,
    attempts: int = 3,
) -> dict[str, Any]:
    context = f"city_id={city_id} materialId={material_id}"
    for attempt in range(attempts):
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
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt + 1 == attempts:
                raise FetchError(f"{context} 美团接口返回 HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            if attempt + 1 == attempts:
                reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
                raise FetchError(f"{context} 无法连接美团接口：{reason}") from exc
        except json.JSONDecodeError as exc:
            if attempt + 1 == attempts:
                raise FetchError(f"{context} 美团接口返回了非 JSON 内容") from exc
        else:
            if isinstance(payload, dict) and payload.get("code") == 0 and payload.get("success") is True:
                return payload
            code = payload.get("code") if isinstance(payload, dict) else None
            message = (
                payload.get("msg") or payload.get("message")
                if isinstance(payload, dict)
                else None
            )
            if code != -1 or attempt + 1 == attempts:
                raise FetchError(
                    f"{context} 美团接口拒绝请求（code={code}, msg={message!r}）"
                )
        time.sleep(2**attempt)
    raise FetchError(f"{context} 美团接口请求失败")  # pragma: no cover


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
    if seed_id not in MATERIAL_IDS:
        raise FetchError("请求模板的种子 materialId 不在五种已确认指数中")
    seed_payload = post_index(template, city_id, seed_id, timeout)
    material_ids = [seed_id, *(item for item in MATERIAL_IDS if item != seed_id)]

    series = [extract_series(seed_payload, city, city_id, seed_id)]
    for material_id in material_ids[1:]:
        if delay:
            time.sleep(delay)
        series.append(
            extract_series(
                post_index(template, city_id, material_id, timeout),
                city,
                city_id,
                material_id,
            )
        )
    return series


def normalize_series(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "city": str(item["city"]),
        "city_id": str(item["city_id"]),
        "disease": str(item["disease"]),
        "disease_id": int(item["disease_id"]),
        "material_id": str(item["material_id"]),
        "points": [[normalize_date(date), float(value)] for date, value in item["points"]],
    }


def history_documents(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        return [json.loads(path.read_text(encoding="utf-8"))]
    if not path.is_dir():
        return []

    manifest_path = path / "manifest.json"
    legacy_path = path / "indexes.json"
    if not manifest_path.exists():
        return [json.loads(legacy_path.read_text(encoding="utf-8"))] if legacy_path.exists() else []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != 2 or not isinstance(manifest.get("cities"), list):
        raise FetchError("历史 manifest.json 格式无效")
    documents = []
    for city in manifest["cities"]:
        relative = Path(str(city.get("file", "")))
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
            raise FetchError("历史 manifest.json 包含无效城市文件路径")
        city_path = path / relative
        if not city_path.is_file():
            raise FetchError(f"缺少历史城市文件：{relative.as_posix()}")
        documents.append(json.loads(city_path.read_text(encoding="utf-8")))
    return documents


def load_history(path: Path | None) -> dict[tuple[str, int], dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    history: dict[tuple[str, int], dict[str, Any]] = {}
    for document in history_documents(path):
        if document.get("version") not in (1, 2) or not isinstance(document.get("series"), list):
            raise FetchError("历史 JSON 格式无效")
        for item in document["series"]:
            if not isinstance(item, dict):
                raise FetchError("历史 JSON 包含无效 series")
            normalized = normalize_series(item)
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


def validate_document(
    document: dict[str, Any], expected_cities: tuple[tuple[str, str], ...] = CITIES
) -> None:
    series = document.get("series")
    if document.get("version") != 1 or not isinstance(series, list):
        raise FetchError("输出 JSON 缺少 version=1 或 series")
    expected = {city_id: city for city, city_id in expected_cities}
    current = {str(item.get("city_id")) for item in series}
    if current != set(expected):
        raise FetchError(f"输出 JSON 只有 {len(current)} 个有效城市，预期 {len(expected)} 个")
    for city_id, city in expected.items():
        city_series = [item for item in series if str(item.get("city_id")) == city_id]
        if len(city_series) != 5:
            raise FetchError(f"{city} 只有 {len(city_series)} 条疾病序列")
        if any(str(item.get("city")) != city for item in city_series):
            raise FetchError(f"city_id={city_id} 的城市名称不一致")
        if any(len(item.get("points") or []) < 14 for item in city_series):
            raise FetchError(f"{city} 至少一条序列少于 14 个数据点")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def write_documents(output_dir: Path, document: dict[str, Any]) -> dict[str, Any]:
    validate_document(document)
    manifest_cities = []
    for city, city_id in CITIES:
        city_series = [item for item in document["series"] if item["city_id"] == city_id]
        relative = f"cities/{city_id}.json"
        write_json(
            output_dir / relative,
            {
                "version": 1,
                "updated_at": document["updated_at"],
                "source": document["source"],
                "city": city,
                "city_id": city_id,
                "series": city_series,
            },
        )
        manifest_cities.append({"city": city, "city_id": city_id, "file": relative})
    manifest = {
        "version": 2,
        "updated_at": document["updated_at"],
        "source": document["source"],
        "cities": manifest_cities,
        "series_count": len(document["series"]),
        "point_count": sum(len(item["points"]) for item in document["series"]),
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def collect(
    template_path: Path,
    history_path: Path | None,
    output_dir: Path,
    timeout: float,
    delay: float,
) -> dict[str, Any]:
    template = load_template(template_path)
    history = load_history(history_path)
    fresh: list[dict[str, Any]] = []
    for index, (city, city_id) in enumerate(CITIES):
        if index and delay:
            time.sleep(delay)
        fresh.extend(fetch_city(template, city, city_id, timeout, delay))
        print(f"已抓取 {city}（{index + 1}/{len(CITIES)}）", flush=True)
    document = {
        "version": 1,
        "updated_at": utc_now(),
        "source": "美团 App 传染病指数",
        "series": merge_series(history, fresh),
    }
    write_documents(output_dir, document)
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=0.3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    document = collect(
        args.template,
        args.history,
        args.output_dir,
        args.timeout,
        args.delay,
    )
    print(
        json.dumps(
            {
                "updated_at": document["updated_at"],
                "cities": len({item["city_id"] for item in document["series"]}),
                "series": len(document["series"]),
                "points": sum(len(item["points"]) for item in document["series"]),
                "output": str(args.output_dir),
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
