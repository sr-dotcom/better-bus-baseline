import zipfile

import duckdb

from ingest.load_gtfs import load


def make_zip(path, trips_rows):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("trips.txt", "route_id,service_id,trip_id\n" + "".join(f"{r}\n" for r in trips_rows))
        z.writestr("calendar_dates.txt", "service_id,date,exception_type\nS1,20261005,1\n")
        z.writestr("readme.md", "ignored")


def test_load_is_idempotent_and_all_text(tmp_path):
    make_zip(tmp_path / "a.zip", ["1,S1,T1", "1,S1,T2"])
    make_zip(tmp_path / "b.zip", ["2,S1,T3"])
    feeds = {"v1": tmp_path / "a.zip", "v2": tmp_path / "b.zip"}
    con = duckdb.connect()
    first = load(con, feeds, tmp_path / "pq", "2026-10-16T00:00:00Z")
    second = load(con, feeds, tmp_path / "pq", "2026-10-16T01:00:00Z")
    assert first == second
    assert first[("raw_trips", "v1")] == 2
    assert first[("raw_trips", "v2")] == 1
    assert first[("raw_calendar_dates", "v1")] == 1
    assert con.execute("select count(*) from raw_trips").fetchone()[0] == 3
    # all source columns are text, even numeric-looking ones
    types = {
        r[0]: r[1]
        for r in con.execute(
            "select column_name, data_type from information_schema.columns where table_name = 'raw_trips'"
        ).fetchall()
    }
    assert set(types.values()) == {"VARCHAR"}
    assert {"feed_version", "loaded_at_utc"} <= set(types)
    assert (tmp_path / "pq" / "raw_trips.parquet").exists()
