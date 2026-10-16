"""Build everything from the raw zips with one command: uv run python analysis/build.py

Order: load the zips (ingest.load_gtfs), run sql/staging, sql/intermediate and sql/marts in file-name order, run the
SQL tests in sql/tests (any returned row is a failure and the exit code is 1), then write each mart to
data/marts/<name>.csv. Tests import build_in_memory() to get the same marts without touching data/bbb.duckdb.
"""

import functools
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingest.load_gtfs import FEEDS, load

SQL = ROOT / "sql"
MODEL_DIRS = ("staging", "intermediate", "marts")
MARTS = (
    "route_period_headway",
    "route_span",
    "express_peak_trips",
    "route_compliance",
    "before_after_headway",
    "before_after",
)
MARTS_DIR = ROOT / "data/marts"


def run_models(con) -> None:
    """Run every model file in staging, intermediate, marts order (file-name order inside a folder)."""
    for folder in MODEL_DIRS:
        for path in sorted((SQL / folder).glob("*.sql")):
            try:
                con.execute(path.read_text(encoding="utf-8"))
            except duckdb.Error as exc:
                raise SystemExit(f"SQL model failed: sql/{folder}/{path.name}\n{exc}") from exc


def run_sql_tests(con) -> list[str]:
    """Run sql/tests/*.sql. Each file returns the offending rows; a row means the test failed.

    The first line `-- test: <what it checks>` names the test. Returns one message per failed test.
    """
    failures = []
    for path in sorted((SQL / "tests").glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        name = next((ln[len("-- test:") :].strip() for ln in text.splitlines() if ln.startswith("-- test:")), path.name)
        cur = con.execute(text)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
        if rows:
            shown = "\n".join("    " + str(dict(zip(cols, r))) for r in rows[:5])
            more = f"\n    ... and {len(rows) - 5} more" if len(rows) > 5 else ""
            failures.append(f"FAIL {path.name}: {name} ({len(rows)} offending rows)\n{shown}{more}")
    return failures


def export_marts(con, out_dir: Path = MARTS_DIR) -> list[Path]:
    """Write each mart to <out_dir>/<name>.csv, ordered by every column so the file is the same on every run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in MARTS:
        path = out_dir / f"{name}.csv"
        con.execute(f"copy (select * from {name} order by all) to '{path.as_posix()}' (format csv, header)")
        paths.append(path)
    return paths


def build(con, parquet_dir: Path) -> None:
    """Load the raw zips into con, then run the models. Parquet goes to parquet_dir."""
    loaded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    load(con, FEEDS, parquet_dir, loaded_at)
    run_models(con)


@functools.cache
def build_in_memory():
    """One in-memory build per process, for tests. Raw zips come from data/raw/; nothing is written under data/."""
    con = duckdb.connect()
    with tempfile.TemporaryDirectory() as tmp:
        build(con, Path(tmp))
    return con


def main() -> int:
    con = duckdb.connect(str(ROOT / "data/bbb.duckdb"))
    build(con, ROOT / "data/parquet")
    print("built staging, intermediate and marts")
    failures = run_sql_tests(con)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        print(f"{len(failures)} SQL test(s) failed", file=sys.stderr)
        return 1
    print(f"SQL tests passed ({len(list((SQL / 'tests').glob('*.sql')))} files)")
    for path in export_marts(con):
        print(
            f"wrote {path.relative_to(ROOT).as_posix()} ({con.execute(f'select count(*) from {path.stem}').fetchone()[0]} rows)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
