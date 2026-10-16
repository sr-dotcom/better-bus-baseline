"""Residents within 800 m of a stop served by a 15-min-tier route, before and after the Oct 5, 2026 change.

Two rows per date. "strict tier": routes in the 15-min tier. "incl. near-miss routes": those routes plus every route
with a 15-min near miss that day (a direction-period the 15-minute standard covers whose median is 901-960 s, the same
rule as the near_miss section of findings.json), buffers dissolved so a resident is counted once.

Run: uv run python analysis/equity.py   (writes data/equity.csv; downloads go to data/census/, which is git-ignored)

Method, in order:
1. Routes: the weekday routes whose tier is "15-min" on each comparison date, read from data/marts/route_compliance.csv.
2. Stops: every stop that an active trip of those routes calls at on that date (active trips and service days come from
   the same SQL models as the marts, built in memory from the zips in data/raw/).
3. Project stops and tracts to a metre CRS (EPSG:32119, NAD83 / North Carolina), buffer each stop by 800 m, dissolve.
4. Area-weighted overlay on census tracts: tract population x (area of tract inside the buffer / tract area), summed.
5. Population: ACS 5-year B01003_001E (total population) per tract from the Census API. Tract shapes: TIGER/Line.

What this is not: area weighting assumes people are spread evenly inside a tract; a 15-min tier is a schedule property,
not delivered service; the buffer is a straight-line distance, not a walking distance; ACS values are estimates with
margins of error that are not carried through here.
"""

import csv
import hashlib
import json
import math
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.findings import LIMIT_15_S, NEAR_MISS_S

BUFFER_M = 800
CRS_M = "EPSG:32119"  # NAD83 / North Carolina, metres
TIGER_YEAR = 2024
ACS_YEAR = 2024  # ACS 5-year, 2020-2024
STATE_FIPS = "37"  # North Carolina; the check in run() confirms the buffers stay inside it
DATES = (("before", "2026-09-30"), ("after", "2026-10-14"))
CENSUS_DIR = ROOT / "data/census"
OUT = ROOT / "data/equity.csv"
TIGER_URL = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}/TRACT/tl_{TIGER_YEAR}_{STATE_FIPS}_tract.zip"
ACS_URL = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
STRICT = "strict tier"
WITH_NEAR_MISS = "incl. near-miss routes"
FIELDS = [
    "scenario",
    "date",
    "side",
    "routes",
    "near_miss_routes_added",
    "n_routes",
    "n_stops",
    "residents",
    "tracts_touched",
    "tracts_without_estimate",
    "buffer_outside_tracts_m2",
    "buffer_m",
    "crs",
    "tiger_vintage",
    "acs_vintage",
    "method",
]
METHOD = (
    "Residents = sum over census tracts of total population (ACS 5-year B01003_001E) x share of the tract's area inside "
    "the union of 800 m straight-line buffers around every stop served on the date by the routes of the row (strict "
    "tier: routes in the 15-min tier; incl. near-miss routes: those plus routes with a 15-min near miss, a covered "
    "direction-period with a median of 901-960 s); area weighting assumes uniform density inside a tract."
)


def stop_buffers(points: gpd.GeoDataFrame, metres: float = BUFFER_M):
    """Dissolve one buffer of `metres` around every point (points already in a metre CRS) into a single geometry."""
    return unary_union(list(points.geometry.buffer(metres)))


def weighted_population(buffer_geom, tracts: gpd.GeoDataFrame, pop_col: str = "pop") -> tuple[float, int, int]:
    """Area-weighted residents inside buffer_geom.

    tracts: a GeoDataFrame in the same metre CRS with a population column. Each tract adds
    pop x (area of tract inside the buffer / tract area). Returns (residents, tracts touched, touched tracts with no
    population estimate). A tract that only touches the buffer along an edge has zero overlap area and is not counted.
    A tract with no estimate adds nothing and is counted, never filled.
    """
    residents = 0.0
    touched = 0
    missing = 0
    for geom, pop in zip(tracts.geometry, tracts[pop_col]):
        overlap = geom.intersection(buffer_geom).area
        if overlap <= 0:
            continue
        touched += 1
        if math.isnan(pop):  # no estimate
            missing += 1
            continue
        residents += pop * overlap / geom.area
    return residents, touched, missing


def http_get(url: str, timeout: int) -> bytes:
    """GET with the operating system's certificate store (the requests package ships its own bundle, which fails
    behind a TLS-inspecting proxy). Errors are reduced to a type or status: the URL may carry the API key."""
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=context) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"download failed: HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(f"download failed: {type(exc).__name__}") from None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download_tracts() -> Path:
    """Download the TIGER/Line tract zip once into data/census/ and record its URL, time and SHA-256."""
    CENSUS_DIR.mkdir(parents=True, exist_ok=True)
    path = CENSUS_DIR / TIGER_URL.rsplit("/", 1)[1]
    if not path.exists():
        path.write_bytes(http_get(TIGER_URL, 300))
        manifest = {
            "url": TIGER_URL,
            "downloaded_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        (CENSUS_DIR / "tiger_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def census_key() -> str:
    """CENSUS_API_KEY from the environment, else from a .env file in the repo root or its parent. Never printed."""
    key = os.environ.get("CENSUS_API_KEY", "")
    for env_file in (ROOT / ".env", ROOT.parent / ".env"):
        if not key and env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("CENSUS_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise SystemExit("CENSUS_API_KEY is not set")
    return key


def fetch_population() -> dict[str, float]:
    """GEOID -> total population (B01003_001E) for every tract in the state; raw JSON kept in data/census/.

    The request URL carries the key, so exceptions are reduced to a status line and never printed as they are.
    """
    CENSUS_DIR.mkdir(parents=True, exist_ok=True)
    raw = CENSUS_DIR / f"acs5_{ACS_YEAR}_B01003_state{STATE_FIPS}_tracts.json"
    if not raw.exists():
        params = {"get": "NAME,B01003_001E", "for": "tract:*", "in": f"state:{STATE_FIPS}", "key": census_key()}
        body = http_get(f"{ACS_URL}?{urllib.parse.urlencode(params)}", 120)
        try:
            json.loads(body)
        except ValueError:
            raise SystemExit("Census API did not return JSON (key rejected or missing?)") from None
        raw.write_bytes(body)
        fetched = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = {"url": ACS_URL, "query": "get=NAME,B01003_001E&for=tract:*&in=state:37", "downloaded_utc": fetched}
        (CENSUS_DIR / "acs_manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    rows = json.loads(raw.read_text(encoding="utf-8"))
    head = rows[0]
    i_pop, i_state, i_county, i_tract = (head.index(c) for c in ("B01003_001E", "state", "county", "tract"))
    out = {}
    for row in rows[1:]:
        value = row[i_pop]
        out[row[i_state] + row[i_county] + row[i_tract]] = float(value) if value not in (None, "") else float("nan")
    return out


def load_tracts() -> gpd.GeoDataFrame:
    tracts = gpd.read_file(f"zip://{download_tracts().as_posix()}")
    population = fetch_population()
    tracts["pop"] = tracts["GEOID"].map(population)
    return tracts.to_crs(CRS_M)


def tier_15_routes() -> dict[str, list[str]]:
    """Weekday routes in the 15-min tier on each comparison date, from the committed route_compliance mart."""
    wanted = {date for _, date in DATES}
    found: dict[str, list[str]] = {date: [] for date in wanted}
    with (ROOT / "data/marts/route_compliance.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["date"] in wanted and row["tier"] == "15-min":
                found[row["date"]].append(row["route_short_name"])
    return {date: sorted(routes) for date, routes in found.items()}


def near_miss_15_routes(headway_rows, date: str) -> list[str]:
    """Routes with at least one direction-period on `date` that the 15-minute standard covers and whose median is above
    900 s by at most 60 s. headway_rows: dicts as read from route_period_headway.csv."""
    found = {
        r["route_short_name"]
        for r in headway_rows
        if r["date"] == date
        and r["covers_15"] == "true"
        and r["headway_median_s"] != ""
        and LIMIT_15_S < float(r["headway_median_s"]) <= LIMIT_15_S + NEAR_MISS_S
    }
    return sorted(found)


def read_headway_rows() -> list[dict]:
    with (ROOT / "data/marts/route_period_headway.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def served_stops(con, date: str, routes: list[str]) -> gpd.GeoDataFrame:
    """Stops that an active trip of the routes calls at on the date (stops open for neither pickup nor drop-off excluded)."""
    if not routes:
        return gpd.GeoDataFrame({"stop_id": []}, geometry=[], crs="EPSG:4326")
    marks = ",".join("?" for _ in routes)
    rows = con.execute(
        f"""
        select distinct p.stop_id, p.stop_lat, p.stop_lon
        from active_trips a
        join stg_stop_times s on s.trip_id = a.trip_id and s.feed_version = a.feed_version
        join stg_stops p on p.stop_id = s.stop_id and p.feed_version = a.feed_version
        where a.date = ? and a.route_short_name in ({marks})
          and not (coalesce(s.pickup_type, 0) = 1 and coalesce(s.drop_off_type, 0) = 1)
        order by p.stop_id
        """,
        [date, *routes],
    ).fetchall()
    return gpd.GeoDataFrame(
        {"stop_id": [r[0] for r in rows]},
        geometry=[Point(r[2], r[1]) for r in rows],
        crs="EPSG:4326",
    )


def run() -> int:
    from analysis.build import build_in_memory

    con = build_in_memory()
    tier_routes = tier_15_routes()
    headway_rows = read_headway_rows()
    tracts = load_tracts()
    tracts_union = unary_union(list(tracts.geometry))
    rows = []
    for scenario in (STRICT, WITH_NEAR_MISS):
        for side, date in DATES:
            added = (
                []
                if scenario == STRICT
                else [r for r in near_miss_15_routes(headway_rows, date) if r not in tier_routes[date]]
            )
            routes = sorted(set(tier_routes[date]) | set(added), key=lambda r: (int(r.rstrip("x")), r))
            stops = served_stops(con, date, routes).to_crs(CRS_M)
            buffer_geom = stop_buffers(stops)
            residents, touched, missing = weighted_population(buffer_geom, tracts)
            outside = buffer_geom.difference(tracts_union).area
            rows.append(
                {
                    "scenario": scenario,
                    "date": date,
                    "side": side,
                    "routes": " ".join(routes),
                    "near_miss_routes_added": " ".join(added),
                    "n_routes": len(routes),
                    "n_stops": len(stops),
                    "residents": round(residents),
                    "tracts_touched": touched,
                    "tracts_without_estimate": missing,
                    "buffer_outside_tracts_m2": round(outside),
                    "buffer_m": BUFFER_M,
                    "crs": CRS_M,
                    "tiger_vintage": TIGER_YEAR,
                    "acs_vintage": f"{ACS_YEAR} 5-year",
                    "method": METHOD,
                }
            )
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print({k: row[k] for k in FIELDS if k != "method"})
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
