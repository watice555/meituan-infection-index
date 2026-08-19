from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.fetch_data import (
    FetchError,
    extract_series,
    load_history,
    merge_series,
    normalize_date,
    validate_document,
    write_document,
)


def sample_payload(city: str = "杭州市", value: float = 100.0) -> dict:
    return {
        "code": 0,
        "success": True,
        "data": {
            "cityName": city,
            "diseaseId": 4,
            "diseaseName": "新冠",
            "cityHealthDetailModule": {
                "diseaseSearchIndexList": [
                    {"date": "20260817", "value": value},
                    {"date": "20260818", "value": 120.0},
                ]
            },
        },
    }


class FetchDataTests(unittest.TestCase):
    def test_normalize_date(self) -> None:
        self.assertEqual(normalize_date("20260818"), "2026-08-18")

    def test_extract_series_validates_city(self) -> None:
        with self.assertRaisesRegex(FetchError, "预期 杭州市"):
            extract_series(sample_payload("上海市"), "杭州市", "330100", "16427")

    def test_merge_revises_overlap_and_preserves_old_points(self) -> None:
        old = extract_series(sample_payload(value=90.0), "杭州市", "330100", "16427")
        old["points"].insert(0, ["2026-08-16", 80.0])
        fresh = extract_series(sample_payload(value=110.0), "杭州市", "330100", "16427")
        result = merge_series({("330100", 4): old}, [fresh])
        self.assertEqual(
            result[0]["points"],
            [["2026-08-16", 80.0], ["2026-08-17", 110.0], ["2026-08-18", 120.0]],
        )

    def test_round_trip_public_document(self) -> None:
        series = []
        for city_number in range(5):
            for disease_id in range(5):
                series.append(
                    {
                        "city": f"城市{city_number}",
                        "city_id": str(100000 + city_number),
                        "disease": f"疾病{disease_id}",
                        "disease_id": disease_id,
                        "material_id": str(16000 + disease_id),
                        "points": [[f"2026-08-{day:02d}", float(day)] for day in range(1, 15)],
                    }
                )
        document = {
            "version": 1,
            "updated_at": "2026-08-19T00:00:00+00:00",
            "source": "test",
            "series": series,
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "indexes.json"
            write_document(output, document)
            loaded = load_history(output)
        self.assertEqual(len(loaded), 25)
        self.assertEqual(loaded[("100000", 0)]["points"][0], ["2026-08-01", 1.0])

    def test_validate_rejects_missing_city(self) -> None:
        with self.assertRaisesRegex(FetchError, "只有 0 个城市"):
            validate_document({"version": 1, "series": []})


if __name__ == "__main__":
    unittest.main()
