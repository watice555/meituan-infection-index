from __future__ import annotations

import json
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.fetch_data import (
    CITIES,
    ENDPOINT,
    FetchError,
    MATERIAL_IDS,
    extract_series,
    load_template,
    load_history,
    merge_series,
    normalize_date,
    post_index,
    validate_document,
    write_documents,
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
    def test_load_template_removes_legacy_dj_token(self) -> None:
        template = {
            "version": 1,
            "endpoint": ENDPOINT,
            "headers": {"content-type": "application/json", "dj-token": "expired"},
            "body": {"materialId": ["16426"]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(template), encoding="utf-8")
            loaded = load_template(path)
        self.assertEqual(loaded["headers"], {"content-type": "application/json"})

    def test_post_index_retries_read_timeout(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(sample_payload()).encode()
        template = {"headers": {}, "body": {"materialId": ["16426"]}}
        with (
            patch(
                "scripts.fetch_data.urllib.request.urlopen",
                side_effect=[socket.timeout("timed out"), response],
            ) as urlopen,
            patch("scripts.fetch_data.time.sleep") as sleep,
        ):
            payload = post_index(template, "330100", "16426", timeout=1)
        self.assertTrue(payload["success"])
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_post_index_retries_generic_business_rejection(self) -> None:
        rejected = MagicMock()
        rejected.__enter__.return_value.read.return_value = json.dumps(
            {"code": -1, "success": False, "msg": None}
        ).encode()
        accepted = MagicMock()
        accepted.__enter__.return_value.read.return_value = json.dumps(sample_payload()).encode()
        template = {"headers": {}, "body": {"materialId": ["16426"]}}
        with (
            patch(
                "scripts.fetch_data.urllib.request.urlopen",
                side_effect=[rejected, accepted],
            ) as urlopen,
            patch("scripts.fetch_data.time.sleep") as sleep,
        ):
            payload = post_index(template, "330100", "16426", timeout=1)
        self.assertTrue(payload["success"])
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)

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
        for city, city_id in CITIES:
            for disease_id in range(1, 6):
                series.append(
                    {
                        "city": city,
                        "city_id": city_id,
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
            output = Path(directory) / "data"
            manifest = write_documents(output, document)
            loaded = load_history(output)
            manifest_on_disk = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(CITIES), 56)
        self.assertEqual(len(loaded), 280)
        self.assertEqual(manifest["version"], 2)
        self.assertEqual(len(manifest_on_disk["cities"]), 56)
        self.assertEqual(loaded[("330100", 1)]["points"][0], ["2026-08-01", 1.0])

    def test_validate_rejects_missing_city(self) -> None:
        with self.assertRaisesRegex(FetchError, "只有 0 个有效城市"):
            validate_document({"version": 1, "series": []})

    def test_city_codes_include_user_confirmed_examples(self) -> None:
        cities = dict(CITIES)
        expected_names = {
            f"{name}市"
            for name in "杭州 上海 北京 深圳 广州 重庆 长沙 成都 长春 常州 大连 东莞 福州 佛山 贵阳 合肥 惠州 呼和浩特 哈尔滨 吉林 济南 金华 江门 昆明 廊坊 洛阳 兰州 临沂 南宁 宁波 南京 青岛 泉州 汕头 石家庄 沈阳 绍兴 苏州 唐山 天津 太原 台州 武汉 潍坊 温州 无锡 芜湖 乌鲁木齐 徐州 西安 厦门 烟台 银川 中山 珠海 郑州".split()
        }
        self.assertEqual(set(cities), expected_names)
        self.assertEqual(len(set(cities.values())), 56)
        self.assertEqual(cities["重庆市"], "500100")
        self.assertEqual(cities["长沙市"], "430100")
        self.assertEqual(cities["成都市"], "510100")
        self.assertEqual(cities["长春市"], "220100")
        self.assertEqual(cities["吉林市"], "220200")
        self.assertEqual(set(MATERIAL_IDS), {"16426", "16427", "16448", "16441", "19625"})


if __name__ == "__main__":
    unittest.main()
