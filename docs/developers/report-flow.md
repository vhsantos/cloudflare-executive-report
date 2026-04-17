# Report and Sync Flow

Developer reference for command behavior, options, cache/history/output files,
and Cloudflare API calls.

## End-to-end flow (with options)

```mermaid
flowchart TD
    START[cf-report command] --> CMD{sync or report}

    CMD -->|sync| S0[parse options and period]
    S0 --> S1[run_sync write_report_json=False]
    S1 --> S2[for each zone/day/stream: process_day]
    S2 --> S3{cache miss or refresh?}
    S3 -->|yes| S4[Cloudflare stream API call]
    S3 -->|no| S5[reuse cached day]
    S4 --> S6[write cache day files]
    S5 --> S7[update zone index]
    S6 --> S7
    S7 --> S8[exit code only no JSON no PDF]

    CMD -->|report| R0[parse options and PDF stream set]
    R0 --> R1[run_report_pdf_command]
    R1 --> R2[resolve period]
    R2 --> R3[build fingerprint]
    R3 --> R4[load current snapshot and validate]
    R4 --> R5{cache-only?}

    R5 -->|yes| C1{snapshot valid and fingerprint match?}
    C1 -->|no| CERR[error no matching snapshot]
    C1 -->|yes| C2{refresh-health?}
    C2 -->|no| C3[reuse snapshot build PDF offline]
    C2 -->|yes| C4{cache complete for selected PDF streams?}
    C4 -->|no| CERR2[error cache incomplete]
    C4 -->|yes| C5[health-only refresh JSON]
    C5 --> C6[Cloudflare zone health API only]
    C6 --> C7[rewrite cf_report.json]
    C7 --> C8[build PDF from refreshed snapshot]

    R5 -->|no| N1{snapshot valid and fingerprint match and not refresh-health?}
    N1 -->|yes| N2[reuse snapshot build PDF offline]
    N1 -->|no| N3{matching snapshot and refresh-health?}
    N3 -->|yes| N4{cache complete for selected PDF streams?}
    N4 -->|yes| N5[health-only refresh JSON then PDF offline]
    N4 -->|no| N6[run_sync write_report_json=True]
    N3 -->|no| N6
    N6 --> N7[Cloudflare stream APIs as needed]
    N7 --> N8[Cloudflare zone metadata and health APIs]
    N8 --> N9[rotate current to previous and history]
    N9 --> N10[write cf_report.json then build PDF]
```

## Option behavior matrix

| Command | Stream API calls | Zone health API calls | Cache writes | JSON writes | PDF |
| --- | --- | --- | --- | --- | --- |
| `sync` | Yes, on cache miss or `--refresh` | No | Yes | No | No |
| `report` | Yes, only when it needs sync path | Yes, in sync path | Maybe | Yes | Yes |
| `report --cache-only` | No | No | No | No | Yes (snapshot reuse only) |
| `report --cache-only --refresh-health` | No | Yes (health only) | No | Yes | Yes |
| `report --refresh-health` | If cache incomplete for PDF streams, sync runs; otherwise no stream sync | Yes | Maybe | Yes | Yes |

## Files and history behavior

- **Cache files**
  - Path root: `cache/`
  - Written by `sync` and by report sync path.
  - Never deleted by report path.

- **Current report JSON**
  - Path: output `cf_report.json`
  - Written by report sync path and by health-only refresh path.
  - Contains fingerprint, report period, partial/missing days, and health timestamp.

- **Report history rotation**
  - On report sync path with default output mode:
    - old current is copied to `cf_report_previous.json`
    - old current is copied to `history/cf_report_<timestamp>.json`
  - Health-only refresh updates current JSON in place (no rotation).

## Cloudflare API call points

- **Stream APIs**: fetcher `process_day` path (`dns/http/security/cache/...`).
- **Zone metadata API**: `get_zone` for each selected zone in sync/refresh paths.
- **Zone health API**: `fetch_zone_health`.
- **No stream API in `--cache-only --refresh-health`** path.

## Source modules

- Main report decision tree: `report/command_flow.py`
- Health-only refresh: `report/health_refresh.py`
- Baseline selection: `report/baseline_selection.py`
- Snapshot IO: `report/snapshot.py`
- Cache completeness helpers: `common/report_cache.py`
- Period bounds helpers: `common/report_period.py`
