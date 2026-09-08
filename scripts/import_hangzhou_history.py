#!/usr/bin/env python3
"""Extract manually recorded Hangzhou indexes from an xlsx file and merge them locally."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any
from xml.etree import ElementTree
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data"
CITY_ID = "330100"
SOURCE_CODE = "manual_hangzhou_xlsx"
DISEASES = {
    "新冠": {"disease": "新冠", "disease_id": 4, "material_id": "16427"},
    "甲流": {"disease": "甲流", "disease_id": 3, "material_id": "16441"},
    "支原体": {"disease": "肺炎支原体感染", "disease_id": 5, "material_id": "19625"},
}
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_REFERENCE = re.compile(r"([A-Z]+)([0-9]+)\Z")


class ImportError(RuntimeError):
    """Raised when the supplied workbook or public data cannot be merged safely."""


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.itertext()) for node in root.findall(f"{{{MAIN_NS}}}si")]


def sheet_path(archive: zipfile.ZipFile, sheet_name: str) -> tuple[str, bool]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    workbook_properties = workbook.find(f"{{{MAIN_NS}}}workbookPr")
    date_1904 = bool(
        workbook_properties is not None
        and workbook_properties.attrib.get("date1904", "0") in ("1", "true")
    )
    relationship_id = None
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            relationship_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            break
    if not relationship_id:
        raise ImportError(f"工作簿缺少工作表：{sheet_name}")

    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib.get("Target", "")
            normalized = target.lstrip("/")
            if normalized.startswith("xl/"):
                return normalized, date_1904
            return "xl/" + normalized, date_1904
    raise ImportError(f"无法定位工作表：{sheet_name}")


def cell_value(cell: ElementTree.Element, strings: list[str]) -> str | float | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{MAIN_NS}}}is")
        return "" if inline is None else "".join(inline.itertext())
    value = cell.findtext(f"{{{MAIN_NS}}}v")
    if value is None:
        return None
    if cell_type == "s":
        try:
            return strings[int(value)]
        except (IndexError, ValueError) as exc:
            raise ImportError("工作簿共享字符串索引无效") from exc
    if cell_type in ("str", "e"):
        return value
    try:
        return float(value)
    except ValueError:
        return value


def workbook_rows(path: Path, sheet_name: str = "杭州") -> tuple[dict[int, dict[str, Any]], bool]:
    try:
        archive = zipfile.ZipFile(path)
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        raise ImportError(f"无法读取 xlsx：{path}") from exc
    with archive:
        strings = shared_strings(archive)
        relative, date_1904 = sheet_path(archive, sheet_name)
        root = ElementTree.fromstring(archive.read(relative))
        rows: dict[int, dict[str, Any]] = {}
        for cell in root.findall(f".//{{{MAIN_NS}}}c"):
            match = CELL_REFERENCE.fullmatch(cell.attrib.get("r", ""))
            if not match:
                continue
            column, row_number = match.groups()
            rows.setdefault(int(row_number), {})[column] = cell_value(cell, strings)
    return rows, date_1904


def excel_date(value: Any, date_1904: bool) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ImportError(f"日期单元格不是 Excel 日期数值：{value!r}")
    origin = dt.datetime(1904, 1, 1) if date_1904 else dt.datetime(1899, 12, 30)
    return (origin + dt.timedelta(days=float(value))).date().isoformat()


def extract_history(path: Path) -> dict[str, Any]:
    rows, date_1904 = workbook_rows(path)
    headers = {column: str(value).strip() for column, value in rows.get(1, {}).items()}
    disease_columns = {
        column: DISEASES[header]
        for column, header in headers.items()
        if header in DISEASES and column in ("B", "C", "D")
    }
    if set(item["disease"] for item in disease_columns.values()) != {
        "新冠", "甲流", "肺炎支原体感染"
    }:
        raise ImportError("杭州工作表缺少新冠、甲流或支原体列")

    points = {item["disease_id"]: {} for item in disease_columns.values()}
    for row_number in sorted(number for number in rows if number > 1):
        row = rows[row_number]
        if row.get("A") is None:
            continue
        date = excel_date(row["A"], date_1904)
        for column, disease in disease_columns.items():
            value = row.get(column)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value <= 0:
                raise ImportError(f"{date} {disease['disease']} 指数无效：{value!r}")
            if date in points[disease["disease_id"]]:
                raise ImportError(f"{disease['disease']} 存在重复日期：{date}")
            points[disease["disease_id"]][date] = float(value)

    series = []
    for disease in sorted(disease_columns.values(), key=lambda item: item["disease_id"]):
        disease_points = points[disease["disease_id"]]
        series.append(
            {
                "city": "杭州市",
                "city_id": CITY_ID,
                **disease,
                "points": [
                    [date, disease_points[date], SOURCE_CODE] for date in sorted(disease_points)
                ],
            }
        )
    return {
        "version": 1,
        "updated_at": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "source": "杭州手工历史（美团 App）",
        "series": series,
    }


def merge_into_public_data(seed: dict[str, Any], data_dir: Path) -> dict[str, int]:
    manifest_path = data_dir / "manifest.json"
    city_path = data_dir / "cities" / f"{CITY_ID}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    city = json.loads(city_path.read_text(encoding="utf-8"))
    if manifest.get("version") != 2 or city.get("version") != 1:
        raise ImportError("本地公开数据版本无效")
    if str(city.get("city_id")) != CITY_ID or not isinstance(city.get("series"), list):
        raise ImportError("本地杭州城市数据格式无效")

    counts = {}
    for manual in seed["series"]:
        matches = [
            item for item in city["series"] if int(item.get("disease_id", -1)) == manual["disease_id"]
        ]
        if len(matches) != 1:
            raise ImportError(f"杭州公开数据无法唯一匹配 {manual['disease']}")
        current = matches[0]
        merged = {point[0]: point for point in manual["points"]}
        merged.update({point[0]: point for point in current["points"]})
        current["points"] = [merged[date] for date in sorted(merged)]
        counts[manual["disease"]] = sum(
            1 for point in current["points"] if len(point) == 3 and point[2] == SOURCE_CODE
        )
    write_json(city_path, city)

    total_points = 0
    manual_points = 0
    for entry in manifest["cities"]:
        document = json.loads((data_dir / entry["file"]).read_text(encoding="utf-8"))
        for item in document["series"]:
            total_points += len(item["points"])
            manual_points += sum(
                1 for point in item["points"] if len(point) == 3 and point[2] == SOURCE_CODE
            )
    manifest["point_count"] = total_points
    manifest["manual_point_count"] = manual_points
    write_json(manifest_path, manifest)
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--seed-output", type=Path)
    parser.add_argument("--data-dir", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.seed_output is None and args.data_dir is None:
        raise ImportError("至少指定 --seed-output 或 --data-dir")
    seed = extract_history(args.xlsx)
    if args.seed_output is not None:
        write_json(args.seed_output, seed)
    counts = merge_into_public_data(seed, args.data_dir) if args.data_dir is not None else {}
    print(
        json.dumps(
            {
                "xlsx": str(args.xlsx),
                "seed_output": str(args.seed_output) if args.seed_output else None,
                "data_dir": str(args.data_dir) if args.data_dir else None,
                "extracted": {item["disease"]: len(item["points"]) for item in seed["series"]},
                "merged_manual_points": counts,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportError, FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc
