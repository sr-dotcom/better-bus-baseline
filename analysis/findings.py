"""Every number the page and the memo show, computed from the committed marts: uv run python analysis/findings.py

Reads data/marts/*.csv (the output of analysis/build.py) plus three small reference inputs
(data/reference/otp.csv, data/reference/cats_claims.csv, data/equity.csv) and writes data/findings.json.
The output is reproducible: no run time is written, keys are sorted, and each input file is listed with the SHA-256
of its content (line endings normalised), so a changed input shows up as a changed hash.

The method is not changed here. Tiers, periods and thresholds come from the marts (docs/metrics.md).
"""

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARTS = ROOT / "data/marts"
OUT = ROOT / "data/findings.json"

FEEDS = {"before": "2026-09-10", "after": "2026-09-29"}
WEEKDAY = {"before": "2026-09-30", "after": "2026-10-14"}
SATURDAY = {"before": "2026-09-26", "after": "2026-10-17"}
SUNDAY = {"before": "2026-09-27", "after": "2026-10-18"}
TIERS = ("15-min", "30-min", "below standard", "no service on date")
TIER_KEYS = {
    "15-min": "15-min",
    "30-min": "30-min",
    "below standard": "below standard",
    "no service on date": "no service",
}
PERIOD_ORDER = {"am_peak": 0, "midday": 1, "pm_peak": 2, "evening": 3, "weekend_day": 4}
LIMIT_15_S = 900
LIMIT_30_S = 1800
NEAR_MISS_S = 60  # reported range: above the limit, up to this many seconds above it
NOTABLE = ("5", "9", "23", "177")
CALLOUT_WEEKEND_ROUTES = ("5", "9")
POLICY = "MPTA-04 (formerly MTC-06)"
EQUITY_NOT_COMPUTED = "equity: not computed in v1"
OTP_GAP_NOTE = "no route-level OTP is published; the latest system figure was not found in public packets"

INPUTS = (
    *(
        f"data/marts/{name}.csv"
        for name in (
            "route_compliance",
            "route_period_headway",
            "route_span",
            "express_peak_trips",
            "before_after",
            "before_after_headway",
            "routes",
        )
    ),
    "data/reference/otp.csv",
    "data/reference/cats_claims.csv",
    "data/equity.csv",
)


# ---------------------------------------------------------------------------------------------------------------
# reading and small helpers
# ---------------------------------------------------------------------------------------------------------------


def read_rows(rel: str) -> list[dict]:
    path = ROOT / rel
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def num(value):
    """CSV text to int or float; empty text to None. 900.0 becomes 900."""
    if value in (None, ""):
        return None
    number = float(value)
    return int(number) if number == int(number) else number


def flag(value):
    return {"true": True, "false": False}.get(value)


def text(value):
    return value if value not in (None, "") else None


def mmss(seconds):
    if seconds is None:
        return None
    minutes = int(seconds // 60)
    rest = seconds - 60 * minutes
    return f"{minutes}:{int(rest):02d}" if rest == int(rest) else f"{minutes}:{rest:04.1f}"


def route_key(route: str):
    return (int(re.match(r"\d+", route).group()), route)


def routes_sorted(routes) -> list[str]:
    return sorted(routes, key=route_key)


def group(routes) -> dict:
    ordered = routes_sorted(routes)
    return {"count": len(ordered), "routes": ordered}


def sha256_text(rel: str) -> str | None:
    path = ROOT / rel
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------------------------------------------


class Data:
    def __init__(self):
        self.compliance = {(r["date"], r["route_short_name"]): r for r in read_rows("data/marts/route_compliance.csv")}
        self.headway = read_rows("data/marts/route_period_headway.csv")
        self.hw_index = {
            (r["date"], r["route_short_name"], int(r["direction_id"]), r["period"]): r for r in self.headway
        }
        self.before_after = {r["route_short_name"]: r for r in read_rows("data/marts/before_after.csv")}
        self.ba_headway = read_rows("data/marts/before_after_headway.csv")
        self.routes = {r["route_short_name"]: r for r in read_rows("data/marts/routes.csv")}
        self.express = read_rows("data/marts/express_peak_trips.csv")
        self.local = routes_sorted(r for r, v in self.routes.items() if v["category"] == "bus")
        self.express_routes = routes_sorted(r for r, v in self.routes.items() if v["category"] == "express")


def dir_period(data: Data, date: str, route: str, direction: int, period: str) -> dict | None:
    r = data.hw_index.get((date, route, direction, period))
    if r is None:
        return None
    median, longest = num(r["headway_median_s"]), num(r["headway_max_s"])
    return {
        "n_departures": int(r["n_departures"]),
        "median_s": median,
        "median_mmss": mmss(median),
        "max_s": longest,
        "max_mmss": mmss(longest),
        "covers_15": flag(r["covers_15"]),
        "covers_30": flag(r["covers_30"]),
        "passes_15": flag(r["passes_15"]),
        "passes_30": flag(r["passes_30"]),
        "reason_15": text(r["reason_15"]),
        "reason_30": text(r["reason_30"]),
    }


# ---------------------------------------------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------------------------------------------


def headline(data: Data) -> dict:
    tiers = {}
    span = {}
    express = {}
    for side, date in WEEKDAY.items():
        rows = [data.compliance[(date, r)] for r in data.local]
        tiers[side] = {"date": date, "feed_version": FEEDS[side]} | {
            TIER_KEYS[tier]: group(r["route_short_name"] for r in rows if r["tier"] == tier) for tier in TIERS
        }
        served = [r for r in rows if r["tier"] != "no service on date"]
        span[side] = {
            "date": date,
            "pass": group(r["route_short_name"] for r in served if r["span_pass"] == "true"),
            "fail": group(r["route_short_name"] for r in served if r["span_pass"] == "false"),
            "no service": group(r["route_short_name"] for r in rows if r["tier"] == "no service on date"),
        }
        ex_rows = [data.compliance[(date, r)] for r in data.express_routes]
        express[side] = {
            "date": date,
            "pass": group(r["route_short_name"] for r in ex_rows if r["express_pass"] == "true"),
            "fail": group(r["route_short_name"] for r in ex_rows if r["express_pass"] == "false"),
            "no service": group(r["route_short_name"] for r in ex_rows if r["no_service_on_date"] == "true"),
        }
    changes = {}
    for label, routes in (
        ("all_routes", list(data.routes)),
        ("local_routes", data.local),
        ("express_routes", data.express_routes),
    ):
        changes[label] = {
            kind: group(r for r in routes if data.before_after[r]["change"] == kind)
            for kind in ("up", "down", "new", "same", "gone")
        }
    return {
        "source": "data/marts/route_compliance.csv and data/marts/before_after.csv",
        "period": {"before": WEEKDAY["before"], "after": WEEKDAY["after"], "day": "Wednesday", "feeds": FEEDS},
        "local_routes": len(data.local),
        "express_routes": len(data.express_routes),
        "tiers": tiers,
        "span_local_routes": span,
        "express_peak_trips": express,
        "before_after_changes": changes,
    }


def routes_table(data: Data) -> dict:
    out = []
    after = WEEKDAY["after"]
    for route in routes_sorted(data.routes):
        meta, ba, rc = data.routes[route], data.before_after[route], data.compliance[(after, route)]
        median = num(rc["weakest_median_s"])
        has_weakest = rc["weakest_direction"] != ""
        if ba["category"] == "express":
            express = {"pass": "pass", "fail": "fail"}.get(
                {"true": "pass", "false": "fail"}.get(rc["express_pass"], ""), "no service"
            )
        else:
            express = None
        out.append(
            {
                "route": route,
                "long_name": meta["route_long_name"],
                "category": meta["category"],
                "tier_before": ba["tier_before"],
                "tier_after": ba["tier_after"],
                "change": ba["change"],
                "weakest_direction_after": int(float(rc["weakest_direction"])) if has_weakest else None,
                "weakest_period_after": text(rc["weakest_period"]),
                "weakest_median_after_s": median,
                "weakest_median_after_mmss": mmss(median),
                "weakest_note": "fewer than 2 departures in period" if has_weakest and median is None else None,
                "span_start_after": text(ba["span_start_after"]),
                "span_end_after": text(ba["span_end_after"]),
                "span_pass_after": flag(ba["span_pass_after"]),
                "express_result_before": _express_result(data, WEEKDAY["before"], route),
                "express_result_after": express,
            }
        )
    return {
        "source": "data/marts/routes.csv, before_after.csv and route_compliance.csv",
        "period": {"before": WEEKDAY["before"], "after": WEEKDAY["after"], "feeds": FEEDS},
        "rows": out,
    }


def _express_result(data: Data, date: str, route: str):
    rc = data.compliance[(date, route)]
    if rc["category"] != "express":
        return None
    return {"true": "pass", "false": "fail"}.get(rc["express_pass"], "no service")


def pair_rows(data: Data, route: str) -> list[dict]:
    """Weekday direction-periods the 30-minute standard covers (AM peak, midday, PM peak), before and after."""
    keys = {
        (d, p)
        for (date, rt, d, p), r in data.hw_index.items()
        if rt == route and date in WEEKDAY.values() and r["covers_30"] == "true"
    }
    rows = []
    for direction, period in sorted(keys, key=lambda k: (k[0], PERIOD_ORDER[k[1]])):
        before = dir_period(data, WEEKDAY["before"], route, direction, period)
        after = dir_period(data, WEEKDAY["after"], route, direction, period)
        change = None
        if before and after and before["median_s"] is not None and after["median_s"] is not None:
            change = after["median_s"] - before["median_s"]
        rows.append(
            {"direction": direction, "period": period, "before": before, "after": after, "median_change_s": change}
        )
    return rows


def flips(rows: list[dict], key: str) -> list[dict]:
    """Direction-periods whose pass or fail changed between the two dates on one standard."""
    return [
        {
            "direction": r["direction"],
            "period": r["period"],
            "before_passes": r["before"][key],
            "after_passes": r["after"][key],
            "median_before_s": r["before"]["median_s"],
            "median_before_mmss": r["before"]["median_mmss"],
            "median_after_s": r["after"]["median_s"],
            "median_after_mmss": r["after"]["median_mmss"],
            "max_before_s": r["before"]["max_s"],
            "max_after_s": r["after"]["max_s"],
            "n_before": r["before"]["n_departures"],
            "n_after": r["after"]["n_departures"],
        }
        for r in rows
        if r["before"] and r["after"] and r["before"][key] is not None and r["before"][key] != r["after"][key]
    ]


def notable_routes(data: Data) -> dict:
    out = {}
    for route in NOTABLE:
        ba = data.before_after[route]
        rows = pair_rows(data, route)
        flipped_15, flipped_30 = flips(rows, "passes_15"), flips(rows, "passes_30")
        entry = {
            "long_name": data.routes[route]["route_long_name"],
            "tier_before": ba["tier_before"],
            "tier_after": ba["tier_after"],
            "change": ba["change"],
            "span_before": {
                "start": text(ba["span_start_before"]),
                "end": text(ba["span_end_before"]),
                "pass": flag(ba["span_pass_before"]),
            },
            "span_after": {
                "start": text(ba["span_start_after"]),
                "end": text(ba["span_end_after"]),
                "pass": flag(ba["span_pass_after"]),
            },
            "direction_periods": rows,
            "flipped_15_min_standard": flipped_15,
            "flipped_30_min_standard": flipped_30,
        }
        if route == "9":
            lost = {(f["direction"], f["period"]) for f in flipped_15}
            others = [r for r in rows if (r["direction"], r["period"]) not in lost]
            entry["other_scored_direction_periods_after"] = {
                "count": len(others),
                "at_or_below_15_min": sum(
                    1 for r in others if r["after"]["median_s"] is not None and r["after"]["median_s"] <= LIMIT_15_S
                ),
            }
        out[route] = entry
    return {
        "source": "data/marts/route_period_headway.csv and before_after.csv",
        "period": {"before": WEEKDAY["before"], "after": WEEKDAY["after"], "feeds": FEEDS},
        "note": "direction_periods are the weekday periods the 30-minute standard covers (AM peak, midday, PM peak); "
        "the 15-minute standard covers AM peak and PM peak only. A flip is a direction-period whose pass or fail changed.",
        "routes": out,
    }


def near_miss(data: Data) -> dict:
    rows = []
    for (date, route, direction, period), r in data.hw_index.items():
        if date not in WEEKDAY.values() or r["headway_median_s"] == "":
            continue
        median = num(r["headway_median_s"])
        for threshold, covered in ((LIMIT_15_S, r["covers_15"] == "true"), (LIMIT_30_S, r["covers_30"] == "true")):
            if covered and threshold < median <= threshold + NEAR_MISS_S:
                rows.append(
                    {
                        "date": date,
                        "route": route,
                        "direction": direction,
                        "period": period,
                        "threshold_s": threshold,
                        "n_departures": int(r["n_departures"]),
                        "median_s": median,
                        "median_mmss": mmss(median),
                        "max_s": num(r["headway_max_s"]),
                        "max_mmss": mmss(num(r["headway_max_s"])),
                    }
                )
    rows.sort(key=lambda x: (x["date"], route_key(x["route"]), x["direction"], PERIOD_ORDER[x["period"]]))
    return {
        "source": "data/marts/route_period_headway.csv",
        "period": {"dates": list(WEEKDAY.values()), "feeds": FEEDS},
        "status": "reported, never scored: a near miss still fails its standard and the tiers do not change",
        "window_s": {
            "15-min": [LIMIT_15_S + 1, LIMIT_15_S + NEAR_MISS_S],
            "30-min": [LIMIT_30_S + 1, LIMIT_30_S + NEAR_MISS_S],
        },
        "rule": "scored direction-period (the standard covers the period) whose median is above the threshold by at most 60 seconds",
        "count": len(rows),
        "rows": rows,
    }


def no_morning_service(data: Data) -> dict:
    date = WEEKDAY["after"]
    local = set(data.local)
    am = [r for (d, rt, _, p), r in data.hw_index.items() if d == date and p == "am_peak" and rt in local]
    rows = [
        {
            "route": r["route_short_name"],
            "long_name": data.routes[r["route_short_name"]]["route_long_name"],
            "direction": int(r["direction_id"]),
            "n_am_peak_departures": int(r["n_departures"]),
        }
        for r in am
        if int(r["n_departures"]) < 2
    ]
    rows.sort(key=lambda x: (route_key(x["route"]), x["direction"]))
    return {
        "source": "data/marts/route_period_headway.csv",
        "period": {
            "date": date,
            "feed_version": FEEDS["after"],
            "am_peak": "06:00:00 up to but not including 09:00:00",
        },
        "rule": "local (category bus) route-directions with fewer than 2 AM-peak departures; fewer than 2 means no headway",
        "route_directions_scored": len(am),
        "count": len(rows),
        "routes": routes_sorted({r["route"] for r in rows}),
        "rows": rows,
    }


def weekend(data: Data) -> dict:
    claims = {r["route_short_name"]: r for r in read_rows("data/reference/cats_claims.csv")}
    by_route: dict[str, dict[str, list]] = {}
    for r in data.ba_headway:
        if r["day_type"] in ("saturday", "sunday") and r["category"] == "bus":
            by_route.setdefault(r["route_short_name"], {"saturday": [], "sunday": []})[r["day_type"]].append(
                {
                    "direction": int(r["direction_id"]),
                    "n_before": num(r["n_before"]),
                    "n_after": num(r["n_after"]),
                    "median_before_s": num(r["median_before_s"]),
                    "median_before_mmss": mmss(num(r["median_before_s"])),
                    "median_after_s": num(r["median_after_s"]),
                    "median_after_mmss": mmss(num(r["median_after_s"])),
                    "max_before_s": num(r["max_before_s"]),
                    "max_after_s": num(r["max_after_s"]),
                }
            )
    routes = []
    for route in data.local:
        ba = data.before_after[route]
        entry = {"route": route, "long_name": data.routes[route]["route_long_name"]}
        for name, status_key in (("saturday", "sat"), ("sunday", "sun")):
            entry[name] = {
                "status_before": ba[f"{status_key}_status_before"],
                "status_after": ba[f"{status_key}_status_after"],
                "directions": sorted(by_route.get(route, {}).get(name, []), key=lambda x: x["direction"]),
            }
        routes.append(entry)
    callouts = {}
    for route in CALLOUT_WEEKEND_ROUTES:
        entry = next(e for e in routes if e["route"] == route)
        claim = claims.get(route)
        after_rows = [d for day in ("saturday", "sunday") for d in entry[day]["directions"]]
        callouts[route] = {
            "claim": (
                {
                    "text": claim["claim_as_published"],
                    "source": claim["source"],
                    "url": claim["url"],
                    "retrieved_utc": claim["retrieved_utc"],
                }
                if claim
                else None
            ),
            "schedule_after": {day: entry[day]["directions"] for day in ("saturday", "sunday")},
            "after_medians_s": sorted({d["median_after_s"] for d in after_rows}),
            "after_longest_gap_s": max(d["max_after_s"] for d in after_rows),
        }
    return {
        "source": "data/marts/before_after_headway.csv, before_after.csv and data/reference/cats_claims.csv",
        "period": {
            "saturday": SATURDAY,
            "sunday": SUNDAY,
            "feeds": FEEDS,
            "daytime": "09:00:00 up to but not including 18:00:00",
        },
        "status": "report only: MPTA-04 (formerly MTC-06) sets no weekend frequency standard, so no weekend value is scored",
        "routes": routes,
        "callouts": callouts,
    }


def otp() -> dict:
    rows = read_rows("data/reference/otp.csv")
    if not rows:
        return {"status": "gap", "note": OTP_GAP_NOTE}
    r = rows[0]
    return {
        "status": "context only",
        "measure": r["measure"],
        "mode": r["mode"],
        "scope": r["scope"],
        "value_pct": num(r["value_pct"]),
        "month": r["month"],
        "same_month_prior_year_pct": num(r["same_month_prior_year_pct"]),
        "source": r["source"],
        "meeting_date": r["meeting_date"],
        "url": r["url"],
        "pdf_page": num(r["pdf_page"]),
        "retrieved_utc": r["retrieved_utc"],
        "definition": r["definition"],
        "route_level_note": r["route_level_note"],
        "period": r["month"],
    }


EQUITY_CAVEATS = (
    "Area weighting assumes people are spread evenly inside a census tract.",
    "A tier is a schedule property of the published timetable, not delivered service.",
    "Each date has one route in the 15-min tier, so the change mostly compares the corridors of two routes.",
    "Distance is a straight line of 800 m, not a walking distance.",
    "ACS values are 5-year estimates with margins of error that are not carried through.",
    "The near-miss row adds routes that miss the 15-minute standard by at most 60 seconds on a median; they still fail it, and the tiers do not change.",
)


def equity_side(r: dict) -> dict:
    return {
        "date": r["date"],
        "routes": r["routes"].split(),
        "near_miss_routes_added": r["near_miss_routes_added"].split(),
        "n_stops": int(r["n_stops"]),
        "residents": int(r["residents"]),
        "tracts_touched": int(r["tracts_touched"]),
        "tracts_without_estimate": int(r["tracts_without_estimate"]),
    }


def equity() -> dict:
    rows = read_rows("data/equity.csv")
    if not rows:
        return {"status": EQUITY_NOT_COMPUTED}
    scenarios = []
    for label in dict.fromkeys(r["scenario"] for r in rows):  # file order: strict tier first
        sides = {r["side"]: equity_side(r) for r in rows if r["scenario"] == label}
        scenarios.append(
            {
                "label": label,
                "before": sides["before"],
                "after": sides["after"],
                "change_residents": sides["after"]["residents"] - sides["before"]["residents"],
            }
        )
    first = rows[0]
    return {
        "status": "computed",
        "source": "data/equity.csv (analysis/equity.py)",
        "method": first["method"],
        "buffer_m": int(first["buffer_m"]),
        "crs": first["crs"],
        "tiger_vintage": int(first["tiger_vintage"]),
        "acs_vintage": first["acs_vintage"],
        "rows": scenarios,
        "caveats": list(EQUITY_CAVEATS),
    }


def limits() -> dict:
    return {
        "source": "data/reference/mtc06.md and docs/metrics.md",
        "cannot_measure": [
            {
                "item": "crowding",
                "clause": "MPTA-04 (formerly MTC-06) 3.2 (load standards)",
                "why": "GTFS holds no boardings or loads",
                "needs": "automatic passenger count data by trip and stop",
            },
            {
                "item": "route-level ridership",
                "clause": "MPTA-04 (formerly MTC-06) 3.0 (route monitoring, passengers per hour)",
                "why": "GTFS holds no boardings; the public board packets give ridership by mode, not by route",
                "needs": "boardings by route from CATS",
            },
            {
                "item": "delivered on-time performance (schedule adherence)",
                "clause": "MPTA-04 (formerly MTC-06) 3.3",
                "why": "the audit reads the published schedule, which holds scheduled times and no observed arrivals",
                "needs": "automatic vehicle location or stop-arrival records per trip with the scheduled time",
            },
            {
                "item": "missed trips and headway as riders see it",
                "clause": "MPTA-04 (formerly MTC-06) 3.7",
                "why": "scheduled spacing only: a trip that did not run, or buses that bunched, are not visible",
                "needs": "the same observed arrival records",
            },
        ],
        "policy_gaps": [
            {
                "gap": "MPTA-04 (formerly MTC-06) defines no peak hours",
                "clauses": "2.4, 3.2, 3.7",
                "quote": "CATS will strive to provide at least 15-minute peak service on high frequency routes",
                "method_choice": "docs/metrics.md decision 1: AM peak 06:00-09:00, midday 09:00-15:00, PM peak 15:00-18:00, evening 18:00-22:00",
            },
            {
                "gap": "MPTA-04 (formerly MTC-06) sets no weekend frequency standard",
                "clauses": "2.4, 3.7",
                "quote": "Common / Local Routes - Bus routes that provide all day service on weekdays and weekends",
                "method_choice": "docs/metrics.md decision 3: weekend headways are reported, with no pass or fail",
            },
            {
                "gap": "the headway and span wording is a goal, not a rule",
                "clauses": "3.7",
                "quote": "As resources become available, CATS will strive to provide",
                "method_choice": "docs/metrics.md: a route that misses a figure is below the goal, not in breach of a hard rule",
            },
            {
                "gap": "exceptions are allowed and depend on data the public does not have",
                "clauses": "3.7",
                "quote": "Exceptions will be based on ridership and productivity.",
                "method_choice": "docs/metrics.md decision 4: no exception is applied; every local route is scored against both 15 and 30 minutes",
            },
            {
                "gap": "the express rule does not say how to pick the peak direction",
                "clauses": "3.7",
                "quote": "Express and Regional Express services will have a minimum of three trips in each peak direction.",
                "method_choice": "docs/metrics.md decision 6: the peak-flow direction, at least 3 trips in the AM peak and in the PM peak",
            },
            {
                "gap": "the on-time trigger is per route and over two service changes, which public data cannot test",
                "clauses": "3.3",
                "quote": "CATS bus routes that achieve an on-time performance score of 80 percent or less over a course of two service changes",
                "method_choice": "docs/metrics.md: context only; the one system-wide figure is in the otp field",
            },
        ],
        "scope": [
            "Schedule-based audit: it scores the published timetable (GTFS), not the buses that ran.",
            "One service change only: MPTA-04 (formerly MTC-06) 3.3 looks over two service changes.",
            "Rail (routes 501 and 510) is out of scope.",
            "Two Wednesdays, not a month: the schedule on those days is read as typical.",
        ],
    }


# ---------------------------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------------------------


def build() -> dict:
    data = Data()
    return {
        "title": "Better Bus Baseline v1: findings",
        "question": "Did the Oct 5, 2026 service change move routes into compliance with MPTA-04 (formerly MTC-06) scheduled frequency and span, "
        "and where does every route stand after it?",
        "generated_by": "analysis/findings.py",
        "policy": {
            "name": POLICY,
            "reference": "data/reference/mtc06.md",
            "note": "Clause numbers and quotes come from data/reference/mtc06.md; sections 3.3 and 3.7 read the same in the "
            "MPTA-04 text (data/reference/mpta04.md).",
        },
        "inputs_sha256": {rel: sha256_text(rel) for rel in INPUTS if (ROOT / rel).exists()},
        "headline": headline(data),
        "routes": routes_table(data),
        "notable_routes": notable_routes(data),
        "near_miss": near_miss(data),
        "no_morning_service": no_morning_service(data),
        "weekend": weekend(data),
        "otp": otp(),
        "equity": equity(),
        "limits": limits(),
    }


def render(findings: dict) -> str:
    return json.dumps(findings, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    findings = build()
    OUT.write_text(render(findings), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()} ({len(findings['routes']['rows'])} routes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
