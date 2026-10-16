"""data/findings.json against the marts, recomputed here with pandas and without the helpers in analysis/findings.py.

Known answers come from docs/known-answers.md and the L3 marts: on Wed 2026-10-14 one local route is in the 15-min tier,
15 in the 30-min tier, 32 below standard; Route 9 loses the 15-min tier on PM-peak direction 0 (11 departures,
median 15:30, max 18:00). The only helper imported from analysis/findings.py is near_miss, for the boundary test.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analysis.findings import near_miss

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "data/marts"
FINDINGS = ROOT / "data/findings.json"
BEFORE, AFTER = "2026-09-30", "2026-10-14"
SAT = ("2026-09-26", "2026-10-17")
SUN = ("2026-09-27", "2026-10-18")


def mart(name):
    return pd.read_csv(MARTS / f"{name}.csv", dtype={"route_short_name": str, "passes_15": str, "passes_30": str})


@pytest.fixture(scope="module")
def f():
    return json.loads(FINDINGS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def compliance():
    return mart("route_compliance")


@pytest.fixture(scope="module")
def headway():
    return mart("route_period_headway")


def none_if_nan(value):
    return None if pd.isna(value) else value


def local_routes(compliance):
    return set(compliance[compliance.category == "bus"].route_short_name)


def routes_of(df):
    return sorted(df.route_short_name, key=lambda r: (int(re.match(r"\d+", r).group()), r))


# --- headline -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("side", "date"), [("before", BEFORE), ("after", AFTER)])
def test_tier_counts_and_routes_match_the_marts(f, compliance, side, date):
    rows = compliance[(compliance.date == date) & (compliance.category == "bus")]
    tiers = f["headline"]["tiers"][side]
    for tier, key in (
        ("15-min", "15-min"),
        ("30-min", "30-min"),
        ("below standard", "below standard"),
        ("no service on date", "no service"),
    ):
        expected = rows[rows.tier == tier]
        assert tiers[key]["count"] == len(expected)
        assert tiers[key]["routes"] == routes_of(expected)
    assert sum(tiers[k]["count"] for k in ("15-min", "30-min", "below standard", "no service")) == 48
    assert f["headline"]["local_routes"] == 48


def test_tier_counts_are_the_hand_checked_known_answers(f):
    # docs/known-answers.md and the L3 finding: after = 1 / 15 / 32 / 0; before = 1 / 16 / 30 / 1 (Route 177 has no trips).
    def counts(side):
        t = f["headline"]["tiers"][side]
        return [t[k]["count"] for k in ("15-min", "30-min", "below standard", "no service")]

    assert counts("after") == [1, 15, 32, 0]
    assert counts("before") == [1, 16, 30, 1]
    assert f["headline"]["tiers"]["after"]["15-min"]["routes"] == ["5"]
    assert f["headline"]["tiers"]["before"]["15-min"]["routes"] == ["9"]


@pytest.mark.parametrize(("side", "date"), [("before", BEFORE), ("after", AFTER)])
def test_span_and_express_counts_match_the_marts(f, compliance, side, date):
    rows = compliance[(compliance.date == date) & (compliance.category == "bus") & (~compliance.no_service_on_date)]
    span = f["headline"]["span_local_routes"][side]
    passed = rows.span_pass.astype(str) == "True"
    assert span["pass"]["routes"] == routes_of(rows[passed])
    assert span["fail"]["routes"] == routes_of(rows[~passed])
    assert span["pass"]["count"] + span["fail"]["count"] + span["no service"]["count"] == 48
    express = compliance[(compliance.date == date) & (compliance.category == "express")]
    ex = f["headline"]["express_peak_trips"][side]
    assert ex["pass"]["routes"] == routes_of(express[express.express_pass == True])
    assert ex["fail"]["routes"] == routes_of(express[express.express_pass == False])
    assert ex["pass"]["count"] + ex["fail"]["count"] + ex["no service"]["count"] == 14


def test_span_boundary_is_the_mart_flag_not_a_rounding(f, compliance):
    # MTC-06 3.7 span: start <= 05:00:00 and end >= 25:30:00 passes. Route 9 starts at 04:50:00 and ends 25:52:00 (pass);
    # Route 5 starts exactly at 05:00:00 after the change (the boundary) and ends 25:54:00, so it passes.
    row5 = next(r for r in f["routes"]["rows"] if r["route"] == "5")
    assert (row5["span_start_after"], row5["span_end_after"], row5["span_pass_after"]) == ("05:00:00", "25:54:00", True)
    assert f["headline"]["span_local_routes"]["after"]["pass"]["routes"] == ["5", "9", "11"]


def test_before_after_changes_match_the_mart(f):
    ba = mart("before_after")
    changes = f["headline"]["before_after_changes"]["all_routes"]
    for kind in ("up", "down", "new", "same", "gone"):
        expected = ba[ba.change == kind]
        assert changes[kind]["count"] == len(expected)
        assert changes[kind]["routes"] == routes_of(expected)
    assert {k: changes[k]["count"] for k in changes} == {"up": 1, "down": 2, "new": 1, "same": 58, "gone": 0}
    assert (
        changes["up"]["routes"] == ["5"]
        and changes["down"]["routes"] == ["9", "23"]
        and changes["new"]["routes"] == ["177"]
    )


# --- routes table ---------------------------------------------------------------------------------------------


def test_routes_table_has_62_rows_and_matches_the_marts(f, compliance):
    rows = f["routes"]["rows"]
    assert len(rows) == 62
    assert len({r["route"] for r in rows}) == 62
    names = pd.read_csv(MARTS / "routes.csv", dtype=str).set_index("route_short_name")
    ba = mart("before_after").set_index("route_short_name")
    after = compliance[compliance.date == AFTER].set_index("route_short_name")
    for r in rows:
        assert r["long_name"] == names.loc[r["route"], "route_long_name"]
        assert r["category"] == names.loc[r["route"], "category"]
        assert (r["tier_before"], r["tier_after"], r["change"]) == tuple(
            ba.loc[r["route"], ["tier_before", "tier_after", "change"]]
        )
        median = after.loc[r["route"], "weakest_median_s"]
        assert r["weakest_median_after_s"] == (None if pd.isna(median) else median)
        if not pd.isna(median):
            assert r["weakest_median_after_mmss"] == f"{int(median // 60)}:{int(median % 60):02d}"
    r9 = next(r for r in rows if r["route"] == "9")
    assert (r9["weakest_direction_after"], r9["weakest_period_after"], r9["weakest_median_after_s"]) == (
        0,
        "pm_peak",
        930,
    )
    assert r9["weakest_median_after_mmss"] == "15:30"


# --- notable routes -------------------------------------------------------------------------------------------


def cell(headway, date, route, direction, period):
    row = headway[
        (headway.date == date)
        & (headway.route_short_name == route)
        & (headway.direction_id == direction)
        & (headway.period == period)
    ]
    assert len(row) == 1
    return row.iloc[0]


def test_route_9_costs_one_pm_peak_direction(f, headway):
    # Known answer (docs/known-answers.md): Route 9 PM peak, direction 0, after: 11 departures, median 15:30, max 18:00.
    n9 = f["notable_routes"]["routes"]["9"]
    assert (n9["tier_before"], n9["tier_after"], n9["change"]) == ("15-min", "30-min", "down")
    [flip] = n9["flipped_15_min_standard"]
    assert (flip["direction"], flip["period"]) == (0, "pm_peak")
    assert (flip["n_after"], flip["median_after_s"], flip["max_after_s"]) == (11, 930, 1080)
    assert (flip["median_after_mmss"], flip["median_before_s"], flip["n_before"]) == ("15:30", 900, 12)
    row = cell(headway, AFTER, "9", 0, "pm_peak")
    assert (row.n_departures, row.headway_median_s, row.headway_max_s) == (11, 930, 1080)
    # The other five scored direction-periods (AM peak, midday, PM peak, two directions) are at 15:00 or better.
    others = headway[
        (headway.date == AFTER)
        & (headway.route_short_name == "9")
        & headway.covers_30
        & ~((headway.direction_id == 0) & (headway.period == "pm_peak"))
    ]
    assert len(others) == 5 and (others.headway_median_s <= 900).all()
    assert n9["other_scored_direction_periods_after"] == {"count": 5, "at_or_below_15_min": 5}
    assert n9["flipped_30_min_standard"] == []


def test_route_5_moves_up_on_all_four_peak_direction_periods(f, headway):
    n5 = f["notable_routes"]["routes"]["5"]
    assert (n5["tier_before"], n5["tier_after"], n5["change"]) == ("30-min", "15-min", "up")
    flips = {(x["direction"], x["period"]): x for x in n5["flipped_15_min_standard"]}
    assert set(flips) == {(0, "am_peak"), (0, "pm_peak"), (1, "am_peak"), (1, "pm_peak")}
    for (d, p), x in flips.items():
        before, after = cell(headway, BEFORE, "5", d, p), cell(headway, AFTER, "5", d, p)
        assert (x["median_before_s"], x["median_after_s"]) == (before.headway_median_s, after.headway_median_s)
        assert x["before_passes"] is False and x["after_passes"] is True and after.headway_median_s == 900


def test_route_23_loses_the_30_minute_tier_by_one_minute_on_one_median(f, headway):
    n23 = f["notable_routes"]["routes"]["23"]
    assert (n23["tier_before"], n23["tier_after"], n23["change"]) == ("30-min", "below standard", "down")
    [flip] = n23["flipped_30_min_standard"]
    before, after = cell(headway, BEFORE, "23", 0, "pm_peak"), cell(headway, AFTER, "23", 0, "pm_peak")
    assert (flip["direction"], flip["period"]) == (0, "pm_peak")
    assert (before.headway_median_s, after.headway_median_s) == (1800, 1860)  # MTC-06 3.7: 30:00 passes, 31:00 fails
    assert (flip["median_before_s"], flip["median_after_s"]) == (1800, 1860)
    assert (flip["n_before"], flip["n_after"], flip["max_before_s"], flip["max_after_s"]) == (6, 6, 1920, 1920)


def test_route_177_is_new_and_below_standard(f, headway):
    n177 = f["notable_routes"]["routes"]["177"]
    assert (n177["tier_before"], n177["tier_after"], n177["change"]) == ("no service on date", "below standard", "new")
    rows = headway[(headway.date == AFTER) & (headway.route_short_name == "177") & headway.covers_30]
    assert len(n177["direction_periods"]) == len(rows) == 6
    for dp in n177["direction_periods"]:
        assert dp["before"] is None
        expected = cell(headway, AFTER, "177", dp["direction"], dp["period"])
        assert dp["after"]["n_departures"] == expected.n_departures
    assert (n177["span_after"]["start"], n177["span_after"]["end"], n177["span_after"]["pass"]) == (
        "09:00:00",
        "17:01:00",
        False,
    )


# --- near miss ------------------------------------------------------------------------------------------------


def test_near_miss_rows_match_an_independent_filter_and_lie_in_the_windows(f, headway):
    wd = headway[headway.date.isin([BEFORE, AFTER]) & headway.headway_median_s.notna()]
    in15 = wd.covers_15 & (wd.headway_median_s > 900) & (wd.headway_median_s <= 960)
    in30 = wd.covers_30 & (wd.headway_median_s > 1800) & (wd.headway_median_s <= 1860)
    expected = {(r.date, r.route_short_name, int(r.direction_id), r.period) for r in wd[in15 | in30].itertuples()}
    got = {(r["date"], r["route"], r["direction"], r["period"]) for r in f["near_miss"]["rows"]}
    assert got == expected and f["near_miss"]["count"] == len(expected) == 10
    for r in f["near_miss"]["rows"]:
        assert r["threshold_s"] in (900, 1800)
        assert r["threshold_s"] + 1 <= r["median_s"] <= r["threshold_s"] + 60
        src = cell(headway, r["date"], r["route"], r["direction"], r["period"])
        assert (r["n_departures"], r["median_s"], r["max_s"]) == (
            src.n_departures,
            src.headway_median_s,
            src.headway_max_s,
        )
    assert "never scored" in f["near_miss"]["status"]
    assert f["near_miss"]["window_s"] == {"15-min": [901, 960], "30-min": [1801, 1860]}


def test_near_miss_window_boundaries():
    # Boundary: 900 and 1800 pass (not listed); 901 and 1801 are the first listed; 960 and 1860 the last; 961 and 1861 are out.
    def row(median, covers_15=True, covers_30=True):
        return {
            "headway_median_s": str(median),
            "headway_max_s": str(median),
            "n_departures": "6",
            "covers_15": str(covers_15).lower(),
            "covers_30": str(covers_30).lower(),
        }

    index = {}
    for i, median in enumerate((900, 901, 960, 961)):
        index[("2026-10-14", f"10{i}", 0, "am_peak")] = row(median, covers_15=True, covers_30=False)
    for i, median in enumerate((1800, 1801, 1860, 1861)):
        index[("2026-10-14", f"20{i}", 0, "midday")] = row(median, covers_15=False, covers_30=True)
    index[("2026-10-14", "300", 0, "evening")] = row(930, covers_15=False, covers_30=False)  # not scored: never listed
    result = near_miss(SimpleNamespace(hw_index=index))
    assert sorted(r["route"] for r in result["rows"]) == ["101", "102", "201", "202"]


# --- no morning service ---------------------------------------------------------------------------------------


def test_no_morning_service_matches_the_marts(f, headway, compliance):
    local = local_routes(compliance)
    am = headway[(headway.date == AFTER) & (headway.period == "am_peak") & headway.route_short_name.isin(local)]
    short = am[am.n_departures < 2]
    got = {(r["route"], r["direction"], r["n_am_peak_departures"]) for r in f["no_morning_service"]["rows"]}
    assert got == {(r.route_short_name, int(r.direction_id), int(r.n_departures)) for r in short.itertuples()}
    assert f["no_morning_service"]["count"] == len(short) == 16
    assert f["no_morning_service"]["route_directions_scored"] == len(am) == 96
    assert set(f["no_morning_service"]["routes"]) == {"28", "35", "42", "43", "50", "51", "59", "177", "222"}


# --- weekend --------------------------------------------------------------------------------------------------


def test_weekend_rows_match_the_marts_and_cover_every_local_route(f, headway, compliance):
    local = local_routes(compliance)
    rows = {r["route"]: r for r in f["weekend"]["routes"]}
    assert set(rows) == local and len(rows) == 48
    ba = mart("before_after").set_index("route_short_name")
    for day, (before_date, after_date), key in (("saturday", SAT, "sat"), ("sunday", SUN, "sun")):
        for route in local:
            assert rows[route][day]["status_before"] == ba.loc[route, f"{key}_status_before"]
            assert rows[route][day]["status_after"] == ba.loc[route, f"{key}_status_after"]
            for d in rows[route][day]["directions"]:
                b = headway[
                    (headway.date == before_date)
                    & (headway.route_short_name == route)
                    & (headway.direction_id == d["direction"])
                    & (headway.period == "weekend_day")
                ]
                a = headway[
                    (headway.date == after_date)
                    & (headway.route_short_name == route)
                    & (headway.direction_id == d["direction"])
                    & (headway.period == "weekend_day")
                ]
                assert d["median_after_s"] == none_if_nan(a.headway_median_s.iloc[0])
                assert d["max_after_s"] == none_if_nan(a.headway_max_s.iloc[0])
                assert d["n_after"] == a.n_departures.iloc[0]
                assert d["median_before_s"] == none_if_nan(b.headway_median_s.iloc[0])
                assert d["n_before"] == b.n_departures.iloc[0]


def test_weekend_routes_5_and_9_known_answers(f):
    # Schedule, after the change (hand-read from the marts): Route 9 median 15:00 on both days in both directions,
    # longest gap 18:00 (direction 0); Route 5 median 20:00, longest gap 23:00 (Saturday direction 0).
    c = f["weekend"]["callouts"]
    assert c["9"]["after_medians_s"] == [900] and c["9"]["after_longest_gap_s"] == 1080
    assert c["5"]["after_medians_s"] == [1200] and c["5"]["after_longest_gap_s"] == 1380
    sat9 = {d["direction"]: d for d in c["9"]["schedule_after"]["saturday"]}
    assert (sat9[0]["n_after"], sat9[1]["n_after"], sat9[0]["max_after_s"], sat9[1]["max_after_s"]) == (
        35,
        36,
        1080,
        900,
    )
    sun5 = {d["direction"]: d for d in c["5"]["schedule_after"]["sunday"]}
    assert (sun5[0]["n_after"], sun5[1]["n_after"], sun5[0]["median_after_s"]) == (27, 27, 1200)
    assert "15-minute, everyday" in c["9"]["claim"]["text"] and "20-minute weekend" in c["5"]["claim"]["text"]
    assert c["9"]["claim"]["url"].startswith("https://www.charlottenc.gov/CATS/")
    assert f["weekend"]["status"].startswith("report only")


# --- otp, equity, limits --------------------------------------------------------------------------------------


def test_otp_and_equity_equal_their_csv(f):
    otp = pd.read_csv(ROOT / "data/reference/otp.csv").iloc[0]
    assert f["otp"]["value_pct"] == otp.value_pct and f["otp"]["month"] == otp.month and f["otp"]["url"] == otp.url
    assert f["otp"]["pdf_page"] == otp.pdf_page and f["otp"]["status"] == "context only"
    eq = pd.read_csv(ROOT / "data/equity.csv").set_index("side")
    for side in ("before", "after"):
        assert f["equity"][side]["residents"] == eq.loc[side, "residents"]
        assert f["equity"][side]["n_stops"] == eq.loc[side, "n_stops"]
        assert f["equity"][side]["tracts_touched"] == eq.loc[side, "tracts_touched"]
    assert f["equity"]["change_residents"] == eq.loc["after", "residents"] - eq.loc["before", "residents"]
    assert len(f["equity"]["caveats"]) >= 4
    assert any("evenly" in c for c in f["equity"]["caveats"])


def mtc06_text():
    """The quoted lines of mtc06.md joined into one string, so a quote that wraps across lines still matches."""
    lines = [
        ln[1:].strip()
        for ln in (ROOT / "data/reference/mtc06.md").read_text(encoding="utf-8").splitlines()
        if ln.startswith(">")
    ]
    return re.sub(r"\s+", " ", " ".join(lines))


def test_policy_quotes_are_verbatim_from_the_policy_file(f):
    text = mtc06_text()
    gaps = f["limits"]["policy_gaps"]
    assert len(gaps) >= 6
    for gap in gaps:
        assert gap["quote"] in text, gap["quote"]
        assert re.match(r"^\d\.\d", gap["clauses"])
    clauses = " ".join(g["clauses"] for g in gaps)
    assert "3.7" in clauses and "3.3" in clauses and "2.4" in clauses
    assert {c["item"] for c in f["limits"]["cannot_measure"]} >= {"crowding", "route-level ridership"}


# --- provenance, reproducibility, boundary --------------------------------------------------------------------


def test_input_hashes_are_the_hashes_of_the_files(f):
    for rel, digest in f["inputs_sha256"].items():
        data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, rel
    assert "data/marts/route_compliance.csv" in f["inputs_sha256"]


def test_findings_json_is_byte_identical_on_rerun():
    before = FINDINGS.read_bytes()
    subprocess.run([sys.executable, str(ROOT / "analysis/findings.py")], check=True, capture_output=True, cwd=ROOT)
    assert FINDINGS.read_bytes() == before


def test_findings_json_has_no_run_time_and_no_nan():
    raw = FINDINGS.read_text(encoding="utf-8")

    def refuse(constant):
        raise AssertionError(f"non-JSON constant {constant}")

    json.loads(raw, parse_constant=refuse)
    assert not re.search(r"generated_at|timestamp", raw)
