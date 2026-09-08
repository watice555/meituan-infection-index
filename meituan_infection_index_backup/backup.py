#!/usr/bin/env python3
"""Download and accumulate the published Meituan index archive locally."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import datetime as dt
import http.client
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://watice555.github.io/meituan-infection-index/data/"
DEFAULT_DATA_DIR = ROOT / "data"
CITY_FILE = re.compile(r"cities/[0-9]{6}\.json\Z")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
AUTOMATIC_SOURCE = "automatic_archive"


class BackupError(RuntimeError):
    """Raised when the public archive cannot be backed up safely."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, attempts: int = 3) -> dict[str, Any]:
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            if not isinstance(payload, dict):
                raise BackupError(f"远端文件不是 JSON 对象：{url}")
            return payload
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt + 1 == attempts:
                raise BackupError(f"下载失败：{url} 返回 HTTP {exc.code}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException) as exc:
            if attempt + 1 == attempts:
                raise BackupError(f"下载失败：无法访问 {url}") from exc
        except json.JSONDecodeError as exc:
            raise BackupError(f"下载失败：{url} 不是有效 JSON") from exc
        time.sleep(2**attempt)
    raise BackupError(f"下载失败：{url}")


def validate_manifest(manifest: dict[str, Any], expected_cities: int) -> list[dict[str, str]]:
    cities = manifest.get("cities")
    if manifest.get("version") != 2 or not isinstance(cities, list):
        raise BackupError("manifest.json 格式无效")
    if len(cities) != expected_cities:
        raise BackupError(f"manifest.json 只有 {len(cities)} 个城市，预期 {expected_cities} 个")
    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in cities:
        if not isinstance(item, dict):
            raise BackupError("manifest.json 包含无效城市")
        city = str(item.get("city", ""))
        city_id = str(item.get("city_id", ""))
        file = str(item.get("file", ""))
        if not city or city_id in seen_ids or not CITY_FILE.fullmatch(file):
            raise BackupError("manifest.json 包含无效或重复城市")
        if file != f"cities/{city_id}.json":
            raise BackupError("manifest.json 的城市文件与 city_id 不一致")
        seen_ids.add(city_id)
        normalized.append({"city": city, "city_id": city_id, "file": file})
    return normalized


def validate_city_document(
    entry: dict[str, str], document: dict[str, Any]
) -> list[dict[str, Any]]:
    if (
        document.get("version") != 1
        or str(document.get("city")) != entry["city"]
        or str(document.get("city_id")) != entry["city_id"]
        or not isinstance(document.get("series"), list)
    ):
        raise BackupError(f"{entry['city']} 的城市文件格式无效")
    series = document["series"]
    if len(series) != 5:
        raise BackupError(f"{entry['city']} 只有 {len(series)} 条疾病序列")

    records: list[dict[str, Any]] = []
    disease_ids: set[int] = set()
    for item in series:
        disease_id = int(item["disease_id"])
        disease = str(item["disease"])
        material_id = str(item["material_id"])
        points = item.get("points")
        if disease_id in disease_ids or not disease or not material_id or not isinstance(points, list):
            raise BackupError(f"{entry['city']} 包含无效或重复疾病序列")
        if len(points) < 14:
            raise BackupError(f"{entry['city']} {disease} 少于 14 个数据点")
        disease_ids.add(disease_id)
        seen_dates: set[str] = set()
        for point in points:
            if not isinstance(point, list) or len(point) not in (2, 3):
                raise BackupError(f"{entry['city']} {disease} 包含无效数据点")
            date, value = str(point[0]), point[1]
            point_source = str(point[2]).strip() if len(point) == 3 else AUTOMATIC_SOURCE
            if not point_source:
                raise BackupError(f"{entry['city']} {disease} 包含空数据来源")
            if not DATE.fullmatch(date) or date in seen_dates:
                raise BackupError(f"{entry['city']} {disease} 包含无效或重复日期")
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise BackupError(f"{entry['city']} {disease} 包含无效指数值")
            seen_dates.add(date)
            records.append(
                {
                    "city_id": entry["city_id"],
                    "city_name": entry["city"],
                    "disease_id": disease_id,
                    "disease_name": disease,
                    "material_id": material_id,
                    "date": date,
                    "index_value": float(value),
                    "point_source": point_source,
                }
            )
    return records


def download_archive(
    base_url: str, expected_cities: int = 56, workers: int = 4
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base_url = base_url.rstrip("/") + "/"
    manifest = fetch_json(base_url + "manifest.json")
    entries = validate_manifest(manifest, expected_cities)
    documents: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_json, base_url + entry["file"]): entry for entry in entries
        }
        for future in as_completed(futures):
            entry = futures[future]
            documents[entry["city_id"]] = future.result()

    records: list[dict[str, Any]] = []
    for entry in entries:
        records.extend(validate_city_document(entry, documents[entry["city_id"]]))
    if int(manifest.get("series_count", -1)) != expected_cities * 5:
        raise BackupError("manifest.json 的序列数与城市数不一致")
    if int(manifest.get("point_count", -1)) != len(records):
        raise BackupError("manifest.json 的数据点数与城市文件不一致")
    return manifest, records


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS infection_index (
            city_id TEXT NOT NULL,
            city_name TEXT NOT NULL,
            disease_id INTEGER NOT NULL,
            disease_name TEXT NOT NULL,
            material_id TEXT NOT NULL,
            date TEXT NOT NULL,
            index_value REAL NOT NULL,
            point_source TEXT NOT NULL DEFAULT 'automatic_archive',
            source_updated_at TEXT NOT NULL,
            backed_up_at TEXT NOT NULL,
            PRIMARY KEY (city_id, disease_id, date)
        );
        CREATE TABLE IF NOT EXISTS backup_runs (
            source_updated_at TEXT PRIMARY KEY,
            backed_up_at TEXT NOT NULL,
            city_count INTEGER NOT NULL,
            series_count INTEGER NOT NULL,
            source_point_count INTEGER NOT NULL,
            local_point_count INTEGER NOT NULL
        );
        """
    )
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(infection_index)")
    }
    if "point_source" not in columns:
        connection.execute(
            "ALTER TABLE infection_index "
            "ADD COLUMN point_source TEXT NOT NULL DEFAULT 'automatic_archive'"
        )


def upsert_records(
    database: Path,
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    backed_up_at: str,
) -> int:
    database.parent.mkdir(parents=True, exist_ok=True)
    source_updated_at = str(manifest["updated_at"])
    with sqlite3.connect(database) as connection:
        initialize_database(connection)
        connection.executemany(
            """
            INSERT INTO infection_index (
                city_id, city_name, disease_id, disease_name, material_id, date,
                index_value, point_source, source_updated_at, backed_up_at
            ) VALUES (
                :city_id, :city_name, :disease_id, :disease_name, :material_id, :date,
                :index_value, :point_source, :source_updated_at, :backed_up_at
            )
            ON CONFLICT (city_id, disease_id, date) DO UPDATE SET
                city_name = excluded.city_name,
                disease_name = excluded.disease_name,
                material_id = excluded.material_id,
                index_value = excluded.index_value,
                point_source = excluded.point_source,
                source_updated_at = excluded.source_updated_at,
                backed_up_at = excluded.backed_up_at
            """,
            [
                {
                    **record,
                    "source_updated_at": source_updated_at,
                    "backed_up_at": backed_up_at,
                }
                for record in records
            ],
        )
        local_point_count = int(
            connection.execute("SELECT COUNT(*) FROM infection_index").fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO backup_runs (
                source_updated_at, backed_up_at, city_count, series_count,
                source_point_count, local_point_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_updated_at) DO UPDATE SET
                backed_up_at = excluded.backed_up_at,
                city_count = excluded.city_count,
                series_count = excluded.series_count,
                source_point_count = excluded.source_point_count,
                local_point_count = excluded.local_point_count
            """,
            (
                source_updated_at,
                backed_up_at,
                len(manifest["cities"]),
                int(manifest["series_count"]),
                int(manifest["point_count"]),
                local_point_count,
            ),
        )
    return local_point_count


def export_csv(database: Path, output: Path) -> int:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT city_id, city_name, disease_id, disease_name, material_id,
                   date, index_value, point_source, source_updated_at, backed_up_at
            FROM infection_index
            ORDER BY city_name, disease_id, date
            """
        ).fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", dir=output.parent,
        prefix=f".{output.name}.", delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys() if rows else ())
        if rows:
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
        temporary = Path(handle.name)
    temporary.replace(output)
    return len(rows)


def write_status(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def backup(base_url: str, data_dir: Path, expected_cities: int = 56) -> dict[str, Any]:
    manifest, records = download_archive(base_url, expected_cities)
    backed_up_at = utc_now()
    database = data_dir / "infection_index.sqlite3"
    csv_path = data_dir / "infection_index.csv"
    local_points = upsert_records(database, manifest, records, backed_up_at)
    exported = export_csv(database, csv_path)
    result = {
        "source_updated_at": str(manifest["updated_at"]),
        "backed_up_at": backed_up_at,
        "cities": len(manifest["cities"]),
        "series": int(manifest["series_count"]),
        "source_points": len(records),
        "local_points": local_points,
        "exported_rows": exported,
        "database": str(database),
        "csv": str(csv_path),
    }
    write_status(data_dir / "last_sync.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--expected-cities", type=int, default=56)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = backup(args.base_url, args.data_dir, args.expected_cities)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BackupError, FileNotFoundError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(f"错误：{exc}") from exc
