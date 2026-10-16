# Better Bus Baseline

A public-data prototype of a performance monitoring plan for CATS (Charlotte Area Transit System) bus service, scored against CATS policy MTC-06 (Transit Service Guidelines).

Version 1 measures the October 5, 2026 service change against CATS policy MTC-06 (scheduled frequency and span), route by route, from published GTFS schedules. The live-feed collector in collector/ is paused until version 1.1.

## Layout

| Folder | Contents |
| --- | --- |
| `data/raw/` | Published GTFS schedule versions, unchanged, with sources in `data/sources.md` |
| `data/reference/` | Small reference files used by the analysis |
| `ingest/` | Loaders into DuckDB and Parquet |
| `sql/` | Staging, intermediate and mart models, plus SQL tests |
| `analysis/` | Analysis scripts |
| `site/` | Static results page |
| `memo/` | Memo |
| `collector/` | GTFS-Realtime poller (paused until version 1.1) |
| `fixtures/`, `tests/` | Small recorded samples and tests (no network calls) |

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
```

Load the saved GTFS schedules into `data/bbb.duckdb` and `data/parquet/` (both git-ignored), then write the service-date probe to `data/probe.md`:

```
uv run python -m ingest.load_gtfs
uv run python -m ingest.probe
```

Run the collector (writes under `DATA_DIR`, default `/data`; set `NTFY_TOPIC` for notifications):

```
DATA_DIR=./data/collector python collector/collect.py
```

All timestamps are stored in UTC.

## License

MIT
