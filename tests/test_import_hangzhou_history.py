from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.import_hangzhou_history import (
    SOURCE_CODE,
    excel_date,
    extract_history,
    merge_into_public_data,
)


def excel_serial(date: dt.date) -> int:
    return (date - dt.date(1899, 12, 30)).days


def write_fixture(path: Path) -> None:
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <workbookPr/><sheets><sheet name="杭州" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    first = excel_serial(dt.date(2024, 12, 19))
    second = excel_serial(dt.date(2024, 12, 20))
    worksheet = f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
 <row r="1"><c r="B1" t="inlineStr"><is><t>新冠</t></is></c><c r="C1" t="inlineStr"><is><t>甲流</t></is></c><c r="D1" t="inlineStr"><is><t>支原体</t></is></c></row>
 <row r="2"><c r="A2"><v>{first}</v></c><c r="B2"><v>70220</v></c><c r="C2"><v>139590</v></c><c r="D2"><v>29080</v></c></row>
 <row r="3"><c r="A3"><v>{second}</v></c><c r="C3"><v>159930</v></c></row>
</sheetData></worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


class ImportHangzhouHistoryTests(unittest.TestCase):
    def test_extracts_numeric_values_without_using_cell_display_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.xlsx"
            write_fixture(path)
            seed = extract_history(path)
        by_disease = {item["disease"]: item["points"] for item in seed["series"]}
        self.assertEqual(
            by_disease["甲流"],
            [
                ["2024-12-19", 139590.0, SOURCE_CODE],
                ["2024-12-20", 159930.0, SOURCE_CODE],
            ],
        )
        self.assertEqual(by_disease["新冠"], [["2024-12-19", 70220.0, SOURCE_CODE]])
        self.assertEqual(by_disease["肺炎支原体感染"], [["2024-12-19", 29080.0, SOURCE_CODE]])

    def test_existing_automatic_point_wins_over_manual_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xlsx = root / "history.xlsx"
            write_fixture(xlsx)
            seed = extract_history(xlsx)
            data = root / "data"
            city_file = data / "cities" / "330100.json"
            city_file.parent.mkdir(parents=True)
            city = {
                "version": 1,
                "city": "杭州市",
                "city_id": "330100",
                "series": [
                    {
                        "city": "杭州市",
                        "city_id": "330100",
                        "disease": item["disease"],
                        "disease_id": item["disease_id"],
                        "material_id": item["material_id"],
                        "points": [["2024-12-19", 999.0]],
                    }
                    for item in seed["series"]
                ],
            }
            city_file.write_text(json.dumps(city), encoding="utf-8")
            (data / "manifest.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "cities": [
                            {"city": "杭州市", "city_id": "330100", "file": "cities/330100.json"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            counts = merge_into_public_data(seed, data)
            merged = json.loads(city_file.read_text(encoding="utf-8"))
            flu = next(item for item in merged["series"] if item["disease"] == "甲流")
            manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(flu["points"][0], ["2024-12-19", 999.0])
        self.assertEqual(flu["points"][1], ["2024-12-20", 159930.0, SOURCE_CODE])
        self.assertEqual(counts["甲流"], 1)
        self.assertEqual(manifest["manual_point_count"], 1)

    def test_excel_1900_date_conversion(self) -> None:
        value = excel_serial(dt.date(2026, 3, 5))
        self.assertEqual(excel_date(value, False), "2026-03-05")


if __name__ == "__main__":
    unittest.main()
