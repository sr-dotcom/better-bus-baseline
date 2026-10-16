"""Load the saved GTFS zips into DuckDB and Parquet, every column as text.

One table per GTFS file (raw_<file>) holding both feeds, with feed_version and loaded_at_utc added.
Each run rebuilds the tables from the zips, so re-running never duplicates rows.

Run from the repo root: uv run python -m ingest.load_gtfs
"""

import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
FEEDS = {
    "2026-09-10": ROOT / "data/raw/mdb-2265-202609100002.zip",
    "2026-09-29": ROOT / "data/raw/mdb-2265-202609290116.zip",
}


def load(con, feeds: dict[str, Path], parquet_dir: Path, loaded_at: str) -> dict[tuple[str, str], int]:
    """Rebuild raw_* tables from the zips. Returns {(table, feed_version): row count}."""
    for t in [
        r[0]
        for r in con.execute(
            "select table_name from information_schema.tables where table_name like 'raw\\_%' escape '\\'"
        ).fetchall()
    ]:
        con.execute(f'drop table "{t}"')
    seen = set()
    with tempfile.TemporaryDirectory() as tmp:  # zips are untrusted: only read the .txt members as data
        for version, zpath in feeds.items():
            with zipfile.ZipFile(zpath) as z:
                for name in sorted(n for n in z.namelist() if n.endswith(".txt")):
                    table = "raw_" + Path(name).stem
                    out = Path(tmp) / f"{version}__{Path(name).name}"
                    out.write_bytes(z.read(name))
                    select = (
                        "select *, ? as feed_version, ? as loaded_at_utc from "
                        "read_csv(?, all_varchar = true, header = true)"
                    )
                    params = [version, loaded_at, out.as_posix()]
                    if table in seen:
                        con.execute(f'insert into "{table}" by name {select}', params)
                    else:
                        con.execute(f'create table "{table}" as {select}', params)
                        seen.add(table)
    parquet_dir.mkdir(parents=True, exist_ok=True)
    for table in sorted(seen):
        con.execute(f"copy \"{table}\" to '{(parquet_dir / (table + '.parquet')).as_posix()}' (format parquet)")
    counts = con.execute(
        " union all ".join(f"select '{t}', feed_version, count(*) from \"{t}\" group by 2" for t in sorted(seen))
    ).fetchall()
    return {(t, v): n for t, v, n in sorted(counts)}


def main() -> None:
    loaded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = duckdb.connect(str(ROOT / "data/bbb.duckdb"))
    counts = load(con, FEEDS, ROOT / "data/parquet", loaded_at)
    print(f"loaded_at_utc {loaded_at}")
    print(f"{'table':24} {'feed_version':12} {'rows':>10}")
    for (t, v), n in counts.items():
        print(f"{t:24} {v:12} {n:>10}")


if __name__ == "__main__":
    main()
