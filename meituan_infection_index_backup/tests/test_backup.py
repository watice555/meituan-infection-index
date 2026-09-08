from __future__ import annotations

import http.client
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backup import (
    AUTOMATIC_SOURCE,
    BackupError,
    export_csv,
    fetch_json,
    initialize_database,
    upsert_records,
    validate_city_document,
    validate_manifest,
)


def sample_manifest(point_count: int = 70) -> dict:
    return {
        "version": 2,
        "updated_at": "2026-08-19T13:28:47+00:00",
        "cities": [{"city": "杭州市", "city_id": "330100", "file": "cities/330100.json"}],
        "series_count": 5,
        "point_count": point_count,
    }


def sample_city(value: float = 100.0) -> dict:
    return {
        "version": 1,
        "city": "杭州市",
        "city_id": "330100",
        "series": [
            {
                "city": "杭州市",
                "city_id": "330100",
                "disease": f"疾病{disease_id}",
                "disease_id": disease_id,
                "material_id": str(16000 + disease_id),
                "points": [[f"2026-08-{day:02d}", value + day] for day in range(1, 15)],
            }
            for disease_id in range(1, 6)
        ],
    }


class BackupTests(unittest.TestCase):
    def test_download_retries_remote_disconnect(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"version":2}'

        with patch(
            "backup.urllib.request.urlopen",
            side_effect=[http.client.RemoteDisconnected("closed"), Response()],
        ), patch("backup.time.sleep"):
            self.assertEqual(fetch_json("https://example.test/manifest.json"), {"version": 2})

    def test_manifest_rejects_path_traversal(self) -> None:
        manifest = sample_manifest()
        manifest["cities"][0]["file"] = "../secret.json"
        with self.assertRaisesRegex(BackupError, "无效或重复城市"):
            validate_manifest(manifest, 1)

    def test_city_document_produces_five_times_fourteen_records(self) -> None:
        entry = validate_manifest(sample_manifest(), 1)[0]
        records = validate_city_document(entry, sample_city())
        self.assertEqual(len(records), 70)
        self.assertEqual(records[0]["city_id"], "330100")
        self.assertEqual(records[0]["point_source"], AUTOMATIC_SOURCE)

    def test_city_document_preserves_manual_point_source(self) -> None:
        entry = validate_manifest(sample_manifest(), 1)[0]
        city = sample_city()
        city["series"][2]["points"][0].append("manual_hangzhou_xlsx")
        records = validate_city_document(entry, city)
        manual = next(
            record
            for record in records
            if record["disease_id"] == 3 and record["date"] == "2026-08-01"
        )
        self.assertEqual(manual["point_source"], "manual_hangzhou_xlsx")

    def test_existing_database_gains_point_source_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    """
                    CREATE TABLE infection_index (
                        city_id TEXT NOT NULL, city_name TEXT NOT NULL,
                        disease_id INTEGER NOT NULL, disease_name TEXT NOT NULL,
                        material_id TEXT NOT NULL, date TEXT NOT NULL,
                        index_value REAL NOT NULL, source_updated_at TEXT NOT NULL,
                        backed_up_at TEXT NOT NULL,
                        PRIMARY KEY (city_id, disease_id, date)
                    )
                    """
                )
                initialize_database(connection)
                columns = {
                    row[1]: row for row in connection.execute("PRAGMA table_info(infection_index)")
                }
        self.assertIn("point_source", columns)
        self.assertEqual(columns["point_source"][4], "'automatic_archive'")

    def test_upsert_revises_overlap_and_preserves_local_history(self) -> None:
        entry = validate_manifest(sample_manifest(), 1)[0]
        initial = validate_city_document(entry, sample_city(100.0))
        revised = validate_city_document(entry, sample_city(200.0))
        old = {**initial[0], "date": "2026-07-31", "index_value": 50.0}
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "backup.sqlite3"
            csv_path = Path(directory) / "backup.csv"
            self.assertEqual(
                upsert_records(database, sample_manifest(), [old, *initial], "2026-08-19T14:00:00+00:00"),
                71,
            )
            self.assertEqual(
                upsert_records(database, sample_manifest(), revised, "2026-08-20T14:00:00+00:00"),
                71,
            )
            self.assertEqual(export_csv(database, csv_path), 71)
            with sqlite3.connect(database) as connection:
                old_value = connection.execute(
                    "SELECT index_value FROM infection_index WHERE date = '2026-07-31'"
                ).fetchone()[0]
                revised_value = connection.execute(
                    "SELECT index_value FROM infection_index WHERE disease_id = 1 AND date = '2026-08-01'"
                ).fetchone()[0]
                revised_source = connection.execute(
                    "SELECT point_source FROM infection_index "
                    "WHERE disease_id = 1 AND date = '2026-08-01'"
                ).fetchone()[0]
            csv_text = csv_path.read_text(encoding="utf-8-sig")
        self.assertEqual(old_value, 50.0)
        self.assertEqual(revised_value, 201.0)
        self.assertEqual(revised_source, AUTOMATIC_SOURCE)
        self.assertIn("杭州市", csv_text)
        self.assertIn("point_source", csv_text.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
