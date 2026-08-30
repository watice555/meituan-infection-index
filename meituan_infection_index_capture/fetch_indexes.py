#!/usr/bin/env python3
"""Fetch every advertised Meituan health index and upsert it into SQLite/CSV."""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import json
from pathlib import Path
import sqlite3
import time
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urlsplit


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = BASE_DIR / "data" / "request_template.json"
DEFAULT_DATABASE = BASE_DIR / "data" / "infection_index.sqlite3"
DEFAULT_CSV = BASE_DIR / "data" / "infection_index.csv"
ALLOWED_ENDPOINT = "https://yiyao-h5.meituan.com/api/v1/health/marketingc/gateway/delivery/hawkeye/index"


class FetchError(RuntimeError):
    pass


def load_template(path: Path) -> dict[str, Any]:
    template = json.loads(path.read_text(encoding="utf-8"))
    if template.get("version") != 1:
        raise FetchError("不支持的私有请求模板版本")
    if template.get("endpoint") != ALLOWED_ENDPOINT:
        raise FetchError("模板目标不是允许的美团指数接口，已拒绝发送 dj-token")
    if not isinstance(template.get("body"), dict):
        raise FetchError("模板缺少 JSON 请求体")
    headers = template.get("headers")
    if not isinstance(headers, dict) or not headers.get("dj-token"):
        raise FetchError("模板缺少 dj-token；请从新的已解密 HAR 重新 bootstrap")
    return template


def fetch_payload(template: dict[str, Any], material_id: str, timeout: float) -> dict[str, Any]:
    body = copy.deepcopy(template["body"])
    body["materialId"] = [str(material_id)]
    body["req_time"] = int(time.time() * 1000)
    request = urllib.request.Request(
        template["endpoint"],
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={str(key): str(value) for key, value in template["headers"].items()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raise FetchError(f"美团接口返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"无法连接美团接口：{exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"美团接口返回非 JSON 内容（HTTP {status}）") from exc
    if not isinstance(payload, dict) or payload.get("code") != 0 or payload.get("success") is not True:
        code = payload.get("code") if isinstance(payload, dict) else None
        message = payload.get("msg") if isinstance(payload, dict) else None
        raise FetchError(
            f"美团接口拒绝请求（code={code}, msg={message!r}）；dj-token 可能已过期，请重新抓取并 bootstrap"
        )
    return payload


def normalize_date(value: Any) -> str:
    raw = str(value)
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise FetchError(f"无法识别指数日期：{raw!r}")


def discover_material_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data") or {}
    module = data.get("cityHealthDetailModule") or {}
    discovered: list[str] = []
    for item in module.get("diseaseStatusList") or []:
        material_id = str(item.get("materialId", "")).strip()
        if material_id and material_id not in discovered:
            discovered.append(material_id)
    return discovered


def extract_records(
    payload: dict[str, Any], material_id: str, fetched_at: str
) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    module = data.get("cityHealthDetailModule") or {}
    series = module.get("diseaseSearchIndexList") or []
    disease_id = data.get("diseaseId")
    disease_name = data.get("diseaseName")
    city_name = data.get("cityName") or module.get("cityName")
    if disease_id is None or not disease_name or not city_name or not series:
        raise FetchError(f"materialId={material_id} 的响应缺少城市、疾病或曲线数据")

    records = []
    for point in series:
        if not isinstance(point, dict) or not isinstance(point.get("value"), (int, float)):
            raise FetchError(f"materialId={material_id} 包含无效曲线点")
        records.append(
            {
                "city_name": str(city_name),
                "disease_id": int(disease_id),
                "disease_name": str(disease_name),
                "material_id": str(material_id),
                "date": normalize_date(point.get("date")),
                "index_value": float(point["value"]),
                "fetched_at": fetched_at,
            }
        )
    return records


def fetch_all(template: dict[str, Any], timeout: float, delay: float) -> list[dict[str, Any]]:
    material_ids = template["body"].get("materialId") or []
    if not material_ids:
        raise FetchError("模板请求体缺少种子 materialId")
    seed_id = str(material_ids[0])
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    seed_payload = fetch_payload(template, seed_id, timeout)
    discovered = discover_material_ids(seed_payload)
    ordered_ids = [seed_id, *(item for item in discovered if item != seed_id)]

    records = extract_records(seed_payload, seed_id, fetched_at)
    for material_id in ordered_ids[1:]:
        if delay:
            time.sleep(delay)
        records.extend(extract_records(fetch_payload(template, material_id, timeout), material_id, fetched_at))
    return records


def upsert_records(database: Path, records: list[dict[str, Any]]) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS infection_index (
                city_name TEXT NOT NULL,
                disease_id INTEGER NOT NULL,
                disease_name TEXT NOT NULL,
                material_id TEXT NOT NULL,
                date TEXT NOT NULL,
                index_value REAL NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (city_name, disease_id, date)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO infection_index (
                city_name, disease_id, disease_name, material_id, date, index_value, fetched_at
            ) VALUES (
                :city_name, :disease_id, :disease_name, :material_id, :date, :index_value, :fetched_at
            )
            ON CONFLICT (city_name, disease_id, date) DO UPDATE SET
                disease_name = excluded.disease_name,
                material_id = excluded.material_id,
                index_value = excluded.index_value,
                fetched_at = excluded.fetched_at
            """,
            records,
        )


def export_csv(database: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT city_name, disease_id, disease_name, material_id, date, index_value, fetched_at
            FROM infection_index
            ORDER BY city_name, disease_id, date
            """
        ).fetchall()
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "city_name",
                "disease_id",
                "disease_name",
                "material_id",
                "date",
                "index_value",
                "fetched_at",
            ),
        )
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=0.25)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    template = load_template(args.template)
    records = fetch_all(template, timeout=args.timeout, delay=args.delay)
    upsert_records(args.database, records)
    row_count = export_csv(args.database, args.csv)
    diseases = sorted({record["disease_name"] for record in records})
    print(
        json.dumps(
            {
                "fetched_records": len(records),
                "stored_rows": row_count,
                "diseases": diseases,
                "database": str(args.database),
                "csv": str(args.csv),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FetchError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc
