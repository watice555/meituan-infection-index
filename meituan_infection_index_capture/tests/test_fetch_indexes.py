from __future__ import annotations

import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from meituan_infection_index_capture.fetch_indexes import (
    discover_material_ids,
    export_csv,
    extract_records,
    normalize_date,
    upsert_records,
)


def sample_payload(value: float = 100.0) -> dict:
    return {
        "code": 0,
        "success": True,
        "data": {
            "diseaseId": 4,
            "diseaseName": "新冠",
            "cityName": "杭州市",
            "cityHealthDetailModule": {
                "diseaseSearchIndexList": [
                    {"date": "20260817", "value": value},
                    {"date": "20260818", "value": 120.0},
                ],
                "diseaseStatusList": [
                    {"materialId": "16427"},
                    {"materialId": "16426"},
                    {"materialId": "16427"},
                ],
            },
        },
    }


class FetchIndexesTests(unittest.TestCase):
    def test_normalizes_compact_date(self) -> None:
        self.assertEqual(normalize_date("20260818"), "2026-08-18")

    def test_discovers_unique_material_ids(self) -> None:
        self.assertEqual(discover_material_ids(sample_payload()), ["16427", "16426"])

    def test_upserts_revisions_and_exports_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "index.sqlite3"
            output = root / "index.csv"
            upsert_records(database, extract_records(sample_payload(100.0), "16427", "first"))
            upsert_records(database, extract_records(sample_payload(111.0), "16427", "second"))
            row_count = export_csv(database, output)

            self.assertEqual(row_count, 2)
            with sqlite3.connect(database) as connection:
                value, fetched_at = connection.execute(
                    "SELECT index_value, fetched_at FROM infection_index WHERE date = '2026-08-17'"
                ).fetchone()
            self.assertEqual(value, 111.0)
            self.assertEqual(fetched_at, "second")
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["date"], "2026-08-17")


if __name__ == "__main__":
    unittest.main()
