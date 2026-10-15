# Better Bus Baseline

A public-data prototype of a performance monitoring plan for CATS (Charlotte Area Transit System) bus service, scored against CATS policy MTC-06 (Transit Service Guidelines).

Everything here is built from free public sources: NTD monthly data, CATS board packets, published GTFS schedule versions, the City of Charlotte bus stops layer, Census ACS, and the CATS GTFS-Realtime feed.

## Layout

| Folder | Contents |
| --- | --- |
| `collector/` | GTFS-Realtime poller that saves raw feed responses |
| `ingest/` | One loader per public archive |
| `sql/` | Staging, intermediate and mart models, plus SQL tests |
| `analysis/`, `dashboard/`, `ai/`, `memo/` | Analysis, dashboard extracts, governed AI layer, memo |
| `fixtures/`, `tests/` | Small recorded samples and tests (no network calls) |

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
```

All timestamps are stored in UTC.

## License

MIT
