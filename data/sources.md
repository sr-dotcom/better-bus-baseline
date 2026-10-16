# Data sources

Raw files in `data/raw/` are saved unchanged. Each entry lists the URL, the download time (UTC), the SHA-256 and the published validation report.

| File | URL | Downloaded (UTC) | SHA-256 | Validation report |
| --- | --- | --- | --- | --- |
| `mdb-2265-202609100002.zip` (feed_version `2026-09-10`, before the Oct 5, 2026 change) | https://files.mobilitydatabase.org/mdb-2265/mdb-2265-202609100002/mdb-2265-202609100002.zip | 2026-10-16T16:34:40Z | `c49786bedc857f795e925928aff3d704dd3c1eaf0f53263f1b1ad874e7801a54` | https://files.mobilitydatabase.org/mdb-2265/mdb-2265-202609100002/report_8.0.1.html |
| `mdb-2265-202609290116.zip` (feed_version `2026-09-29`, after the Oct 5, 2026 change) | https://files.mobilitydatabase.org/mdb-2265/mdb-2265-202609290116/mdb-2265-202609290116.zip | 2026-10-16T16:34:42Z | `5722a19692d66415694f40f86edd840d9506dcd4dde8d4c68326f2be4f08b78f` | https://files.mobilitydatabase.org/mdb-2265/mdb-2265-202609290116/report_8.0.1.html |

## Census data for the equity count (`analysis/equity.py`)

Downloaded by `analysis/equity.py` into `data/census/`, which is git-ignored (the files are not stored in this repository). Only the small result `data/equity.csv` is committed.

| Item | URL | Vintage | Downloaded (UTC) | SHA-256 |
| --- | --- | --- | --- | --- |
| TIGER/Line 2024 census tract shapes, North Carolina (`tl_2024_37_tract.zip`, 20,071,906 bytes) | https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_37_tract.zip | TIGER/Line 2024 (2020 tracts) | 2026-10-16T19:46:59Z | `55020d01d899e244dbbfdd0c876bf01a5e8f1077905faa4302ef0eb87dc47444` |
| ACS 5-year total population, table B01003, estimate B01003_001E, every tract in North Carolina | https://api.census.gov/data/2024/acs/acs5 (query: `get=NAME,B01003_001E&for=tract:*&in=state:37`; an API key is required and is not recorded) | ACS 2020-2024 5-year | 2026-10-16T19:47:01Z | not applicable (API response, kept as `data/census/acs5_2024_B01003_state37_tracts.json`) |
