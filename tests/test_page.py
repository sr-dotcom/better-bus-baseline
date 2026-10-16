"""The results page (site/build/index.html) against data/findings.json and the marts.

The page is built by `npm run build` in site/ (CI builds it before pytest). If the build is missing this test fails
in CI and skips locally with the reason shown, so it never passes silently in CI.

Known answers (the L4 findings, Wed 2026-09-30 before, Wed 2026-10-14 after): local routes at 15-min 1, 30-min 15,
below standard 32 after; 1, 16, 30 and one route with no service before. Route 9 PM peak direction 0: median 15:30.
"""

import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "site/build"
INDEX = BUILD / "index.html"
FINDINGS = json.loads((ROOT / "data/findings.json").read_text(encoding="utf-8"))
MARTS = ROOT / "data/marts"

# Internal paths and document names that must never reach the public page. Personal names are checked by the
# repository leak check, not here.
# The fragments are split so that this file does not itself contain the strings it forbids.
INTERNAL = re.compile(
    "|".join(
        "".join(parts)
        for parts in [
            (r"C:[/\\]Us", "ers"),
            ("/c/", "Users"),
            (r"PLAN\.m", "d"),
            (r"STATUS\.m", "d"),
            (r"CLAUDE\.m", "d"),
            (r"ADR-[0-9]",),
            ("better-", "bus-hq"),
        ]
    )
)
TIER_KEYS = ["15-min", "30-min", "below standard", "no service"]

# Headline numbers the page must show, as paths into findings.json.
REQUIRED_METRICS = (
    ["headline.local_routes", "headline.express_routes"]
    + [
        f"headline.tiers.{when}.{t}.count"
        for when in ("before", "after")
        for t in TIER_KEYS
        if (when, t) != ("after", "no service")
    ]
    + [f"headline.span_local_routes.{when}.pass.count" for when in ("before", "after")]
    + [f"headline.express_peak_trips.{when}.pass.count" for when in ("before", "after")]
    + ["no_morning_service.count", "otp.value_pct", "otp.same_month_prior_year_pct"]
    + [f"equity.rows.{i}.{k}" for i in (0, 1) for k in ("before.residents", "after.residents", "change_residents")]
)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metrics = []  # (path, text)
        self.route_rows = {}  # route -> {col: text}
        self.rects = {}  # (series, tier) -> value
        self.svg_text = {}  # (series, tier) -> text
        self.text = []
        self._metric = None
        self._row = None
        self._svg_text = None
        self.in_footer = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-metric" in a:
            self._metric = [a["data-metric"], ""]
        if tag == "tr" and "data-route" in a:
            self._row = {"route": a["data-route"]}
        elif tag == "td" and self._row is not None:
            self._row.setdefault("_cells", [])
            self._row["_cells"].append("")
        if tag == "rect" and "data-series" in a:
            self.rects[(a["data-series"], a["data-tier"])] = int(a["data-value"])
        if tag == "text" and "data-series" in a:
            self._svg_text = (a["data-series"], a["data-tier"], "")
        if tag == "footer":
            self.in_footer = True

    def handle_endtag(self, tag):
        if self._metric and tag in ("span", "td"):
            self.metrics.append(tuple(self._metric))
            self._metric = None
        if tag == "tr" and self._row is not None:
            cells = self._row.pop("_cells")
            self._row.update(before=cells[3], after=cells[4], change=cells[5])
            self.route_rows[self._row["route"]] = self._row
            self._row = None
        if tag == "text" and self._svg_text:
            s, t, v = self._svg_text
            self.svg_text[(s, t)] = int(v)
            self._svg_text = None
        if tag == "footer":
            self.in_footer = False

    def handle_data(self, data):
        self.text.append(data)
        if self._metric is not None:
            self._metric[1] += data
        if self._row is not None and self._row.get("_cells"):
            self._row["_cells"][-1] += data
        if self._svg_text:
            s, t, v = self._svg_text
            self._svg_text = (s, t, v + data)


@pytest.fixture(scope="module")
def html():
    if not INDEX.exists():
        msg = f"{INDEX} is missing: run `npm ci && npm run build` in site/ first"
        if os.environ.get("CI"):
            pytest.fail(msg)
        pytest.skip(msg)
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page(html):
    p = Page()
    p.feed(html)
    return p


def resolve(path):
    value = FINDINGS
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def as_int(text):
    return int(text.strip().replace(",", "").replace("+", ""))


# --- headline numbers --------------------------------------------------------------------------------------------


def test_known_answer_headline_numbers(page):
    """Known answers from the L4 findings; see the module docstring."""
    shown = {path: as_int(text) for path, text in page.metrics}
    assert [shown[f"headline.tiers.after.{t}.count"] for t in ("15-min", "30-min", "below standard")] == [1, 15, 32]
    assert [shown[f"headline.tiers.before.{t}.count"] for t in TIER_KEYS] == [1, 16, 30, 1]
    assert shown["headline.local_routes"] == 48


def test_every_headline_number_is_on_the_page_and_equals_findings(page):
    shown = {}
    for path, text in page.metrics:
        shown[path] = as_int(text)
    missing = [p for p in REQUIRED_METRICS if p not in shown]
    assert not missing, f"not on the page: {missing}"
    for path, value in shown.items():
        assert value == resolve(path), f"{path}: page {value} != findings {resolve(path)}"


def test_route_9_nuance_text(page):
    """Route 9 PM peak direction 0: median 15:30, 11 departures, longest gap 18:00 (5 of 6 direction-periods pass)."""
    text = " ".join(page.text)
    assert "5 of 6 scored weekday direction-periods" in text
    assert "median 15:30 (before: 15:00), 11 departures, longest gap 18:00" in text


# --- route table -------------------------------------------------------------------------------------------------


def test_route_table_has_62_rows_matching_the_marts(page):
    routes = pd.read_csv(MARTS / "routes.csv", dtype=str)
    ba = pd.read_csv(MARTS / "before_after.csv", dtype=str).set_index("route_short_name")
    assert len(page.route_rows) == 62
    assert set(page.route_rows) == set(routes.route_short_name)
    for route, row in page.route_rows.items():
        assert row["before"] == ba.loc[route, "tier_before"], route
        assert row["after"] == ba.loc[route, "tier_after"], route
        assert row["change"] == ba.loc[route, "change"], route


# --- chart -------------------------------------------------------------------------------------------------------


def test_chart_values_match_findings(page):
    tiers = FINDINGS["headline"]["tiers"]
    expected = {(s, t): tiers[s][t]["count"] for s in ("before", "after") for t in TIER_KEYS}
    assert len(expected) == 8
    assert page.rects == expected
    assert page.svg_text == expected  # the labels drawn on the bars say the same
    for s in ("before", "after"):
        assert sum(v for (series, _), v in page.rects.items() if series == s) == FINDINGS["headline"]["local_routes"]


# --- footer, build, boundary -------------------------------------------------------------------------------------


def test_footer_author_date_and_repo(html):
    footer = html[html.index("<footer") : html.index("</footer>")]
    assert "Naga Sathwik Reddy Gona" in footer
    assert re.search(
        r"<time datetime=\"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\">\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ</time>", footer
    )
    assert "https://github.com/sr-dotcom/better-bus-baseline" in footer


def test_cname_is_exactly_the_domain():
    assert (BUILD / "CNAME").read_text(encoding="utf-8").strip() == "bus.gnsr.dev"


def test_no_internal_paths_or_documents_in_the_build(html):
    hits = []
    for path in BUILD.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".js", ".css", ".json", ".txt", ".webmanifest", ".md"}:
            for m in INTERNAL.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                hits.append(f"{path.relative_to(BUILD)}: {m.group(0)}")
    assert not hits, hits[:10]
