from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_tag = ""
        self.text: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current_tag = tag

    def handle_endtag(self, tag: str) -> None:
        self.current_tag = ""

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.text.append((self.current_tag, value))


class PageTests(unittest.TestCase):
    def test_page_contains_only_requested_sections(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        parser = TextCollector()
        parser.feed(html)
        self.assertIn(("h1", "美团指数存档"), parser.text)
        self.assertIn(
            ("p", "选择城市、病种和起始日期，查看并导出美团指数历史数据。"),
            parser.text,
        )
        self.assertEqual([text for tag, text in parser.text if tag == "h2"], ["趋势图", "列表数据"])
        for removed in (
            "非官方历史记录",
            "每天留住滚动的 14 天",
            "读数说明",
            "最新指数",
            "区间变化",
            "区间峰值",
            "历史天数",
        ):
            self.assertNotIn(removed, html)

    def test_custom_start_date_is_wired_to_filter_and_url(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="start-date" type="date"', html)
        self.assertIn('date >= state.startDate', javascript)
        self.assertIn('url.searchParams.set("start", state.startDate)', javascript)
        self.assertIn('state.range = state.startDate ? "custom" : "all"', javascript)


if __name__ == "__main__":
    unittest.main()
