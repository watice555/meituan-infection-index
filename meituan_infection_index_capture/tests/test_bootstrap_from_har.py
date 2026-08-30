from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from meituan_infection_index_capture.bootstrap_from_har import build_template, write_private_json


class BootstrapFromHarTests(unittest.TestCase):
    def test_strips_query_and_account_identifiers(self) -> None:
        request = {
            "url": (
                "https://yiyao-h5.meituan.com/api/v1/health/marketingc/"
                "gateway/delivery/hawkeye/index?mtgsig=secret"
            ),
            "headers": [
                {"name": "Cookie", "value": "private"},
                {"name": "dj-token", "value": "required"},
                {"name": "User-Agent", "value": "test"},
            ],
            "postData": {
                "text": json.dumps(
                    {
                        "materialId": ["16426"],
                        "req_time": 123,
                        "token": "private",
                        "address": "private",
                        "wm_uuid": "private",
                    }
                )
            },
        }
        template = build_template(request, "captured")
        self.assertEqual(
            template["endpoint"],
            "https://yiyao-h5.meituan.com/api/v1/health/marketingc/gateway/delivery/hawkeye/index",
        )
        self.assertEqual(template["headers"], {"dj-token": "required", "user-agent": "test"})
        self.assertEqual(template["body"]["req_time"], 0)
        self.assertFalse(template["body"]["token"])
        self.assertFalse(template["body"]["address"])
        self.assertFalse(template["body"]["wm_uuid"])

    def test_private_template_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request_template.json"
            write_private_json(path, {"secret": "value"})
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
