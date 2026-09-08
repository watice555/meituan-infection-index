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
            ("p", "选择城市、病种和日期范围，查看并导出美团指数历史数据。"),
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

    def test_custom_date_range_is_wired_to_filter_and_url(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="start-date" type="date"', html)
        self.assertIn('id="end-date" type="date"', html)
        self.assertIn('date >= state.startDate && date <= state.endDate', javascript)
        self.assertIn('url.searchParams.set("start", state.startDate)', javascript)
        self.assertIn('url.searchParams.set("end", state.endDate)', javascript)
        self.assertIn('state.endDate = state.endDate || series.points.at(-1)[0]', javascript)

    def test_page_loads_manifest_then_selected_city_only(self) -> None:
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('fetch("./data/manifest.json"', javascript)
        self.assertIn('fetch(`./data/${record.file}`', javascript)
        self.assertIn("manifest.version !== 2", javascript)
        self.assertNotIn('fetch("./data/indexes.json"', javascript)

    def test_missing_dates_use_calendar_spacing_and_break_the_line(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="coverage-summary"', html)
        self.assertIn("折线不会跨过数据缺口", html)
        self.assertIn("function splitSegments(points)", javascript)
        self.assertIn("point.time - current.at(-1).time > dayMilliseconds", javascript)
        self.assertIn("(times[index] - minTime) / timeSpread", javascript)
        self.assertNotIn("index / (points.length - 1)", javascript)
        self.assertIn("rawMax / rawMin >= 20", javascript)
        self.assertIn("纵轴自动使用对数比例", javascript)

    def test_calendar_ranges_and_point_sources_are_visible(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("记录来源", html)
        self.assertIn('point[2] === "manual_hangzhou_xlsx"', javascript)
        self.assertIn("latest.setDate(latest.getDate() - Number(state.range) + 1)", javascript)
        self.assertIn("function visibleBounds(series, points)", javascript)
        self.assertIn('["date", "city", "disease", "index_value", "source"]', javascript)

    def test_year_range_and_related_links_are_present(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-range="365"', html)
        self.assertIn(">365 天</button>", html)
        self.assertIn('["14", "30", "90", "365", "all"]', javascript)
        self.assertIn('href="https://watice555.github.io/flu_weekly/"', html)
        self.assertIn("流感样病例周报存档", html)
        self.assertIn('href="mailto:wuth.5@qq.com"', html)
        self.assertIn("贡献历史数据：wuth.5@qq.com", html)


if __name__ == "__main__":
    unittest.main()
