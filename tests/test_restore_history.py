from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.restore_history import RestoreError, restore


class RestoreHistoryTests(unittest.TestCase):
    def test_restore_city_shards(self) -> None:
        manifest = {
            "version": 2,
            "cities": [
                {"city": "杭州市", "city_id": "330100", "file": "cities/330100.json"}
            ],
        }
        city = {
            "version": 1,
            "city": "杭州市",
            "city_id": "330100",
            "series": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "history"
            with patch("scripts.restore_history.fetch_json", side_effect=[manifest, city]):
                result = restore("https://example.test/data", output)
            restored = json.loads((output / "cities" / "330100.json").read_text(encoding="utf-8"))
        self.assertEqual(result, "sharded")
        self.assertEqual(restored["city_id"], "330100")

    def test_restore_legacy_combined_json(self) -> None:
        legacy = {"version": 1, "series": []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "history"
            with patch("scripts.restore_history.fetch_json", side_effect=[None, legacy]):
                result = restore("https://example.test/data/", output)
            self.assertTrue((output / "indexes.json").is_file())
        self.assertEqual(result, "legacy")

    def test_restore_rejects_unsafe_city_path(self) -> None:
        manifest = {
            "version": 2,
            "cities": [{"city": "杭州市", "city_id": "330100", "file": "../secret.json"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.restore_history.fetch_json", return_value=manifest):
                with self.assertRaisesRegex(RestoreError, "无效城市文件路径"):
                    restore("https://example.test/data/", Path(directory))


if __name__ == "__main__":
    unittest.main()
