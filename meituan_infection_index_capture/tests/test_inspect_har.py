from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from meituan_infection_index_capture.inspect_har import inspect_har


class InspectHarTests(unittest.TestCase):
    def write_har(self, response_payload: object) -> Path:
        directory = Path(tempfile.mkdtemp())
        path = directory / "capture.har"
        path.write_text(
            json.dumps(
                {
                    "log": {
                        "entries": [
                            {
                                "request": {
                                    "method": "GET",
                                    "url": "https://example.test/disease/trend?mtgsig=secret",
                                },
                                "response": {
                                    "status": 200,
                                    "content": {"mimeType": "application/json", "text": json.dumps(response_payload)},
                                },
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_parallel_date_and_value_arrays(self) -> None:
        path = self.write_har(
            {"data": {"dates": ["2026-08-18", "2026-08-19"], "values": [141.77, 146.03]}}
        )
        candidates = inspect_har(path)
        self.assertEqual(candidates[0]["points"][1], {"date": "2026-08-19", "value": 146.03})
        self.assertIn("disease", candidates[0]["matched_keywords"])
        self.assertEqual(candidates[0]["url"], "https://example.test/disease/trend")

    def test_list_of_date_value_rows(self) -> None:
        path = self.write_har(
            {"data": [{"date": "20260818", "index": 10}, {"date": "20260819", "index": 12}]}
        )
        candidates = inspect_har(path)
        self.assertEqual(candidates[0]["json_path"], "$.data")
        self.assertEqual(len(candidates[0]["points"]), 2)

    def test_ignores_unrelated_json(self) -> None:
        path = self.write_har({"message": "ok", "items": [1, 2, 3]})
        self.assertEqual(inspect_har(path), [])


if __name__ == "__main__":
    unittest.main()
