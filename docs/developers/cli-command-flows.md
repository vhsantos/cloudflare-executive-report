# CLI Command Flows (Full Source Evaluation)

Built from all files under `src`.

## Source Map

- CLI: `src/cloudflare_executive_report/cli.py`
- CLI validation: `src/cloudflare_executive_report/cli_common.py`
- Sync core: `src/cloudflare_executive_report/sync/orchestrator.py`
- Day processing: `src/cloudflare_executive_report/sync/day_processor.py`
- Fetchers registry/protocol: `src/cloudflare_executive_report/fetchers/registry.py`, `src/cloudflare_executive_report/fetchers/types.py`
- Fetchers implementations: `src/cloudflare_executive_report/fetchers/*.py`
- Cache files/index/lock: `src/cloudflare_executive_report/cache/*.py`
- Aggregation: `src/cloudflare_executive_report/aggregate.py`
- Executive rules/summary: `src/cloudflare_executive_report/executive/*.py`
- PDF build: `src/cloudflare_executive_report/pdf/orchestrate.py`
- PDF cache loaders: `src/cloudflare_executive_report/pdf/loader.py`
- Zone health: `src/cloudflare_executive_report/zone_health.py`

## Runtime Architecture

```mermaid
flowchart LR
    CLI[Typer commands] --> OPTS[SyncOptions validation]
    OPTS --> SYNC[run_sync]
    SYNC --> CACHE[cache day envelopes + _index.json]
    SYNC --> JSON[cf_report.json]
    JSON --> ROTATE[previous + history rotation]
    CLI --> PDF[write_report_pdf]
    PDF --> CACHE
    PDF --> HEALTH[fetch_zone_health REST]
```

## Compute report period for PDF (exact meaning)

Called by `cmd_report`:

- `pdf_report_period_for_options(cfg, sync_opts, zone_filter=...)`

Internal logic:

1. Resolve selected zones (by id/name or all).
2. Set `y = utc_yesterday()`.
3. Call `_report_bounds_from_indices(...)`:
   - semantic flags -> `_semantic_current_bounds`
   - `--last N` -> `last_n_complete_days`
   - `--start/--end` -> direct range
   - incremental -> scan zone `_index.json` earliest/latest for selected streams
4. If `--include-today`, force end date to `utc_today()`.
5. Return `(start, end)` for `ReportSpec`.

This is date-boundary computation only; no fetch on its own.

## `cf-report report` (exact flow)

```mermaid
flowchart TD
    A[cmd_report] --> B[_parse_sync_types]
    B --> C[validate_and_build_sync_options]
    C --> D[load_app_config + resolve_zone_filter]
    D --> E{cache_only}
    E -- false --> F[run_sync]
    E -- true --> G[cache_has_any_zone_data guard]
    F --> H[pdf_report_period_for_options]
    G --> H
    H --> I[ReportSpec]
    I --> J[write_report_pdf]
    J --> K[load_*_for_range from cache]
    K --> L[fetch_zone_health via CloudflareClient]
    L --> M[build_executive_summary + stream pages]
    M --> N[build PDF]
```

### `report` side effects

- Cloudflare API
  - Non-cache-only: yes during sync for selected streams and `get_zone`.
  - Cache-only: PDF still calls `fetch_zone_health(..., skip=False)` currently.
- Cache writes
  - Non-cache-only: yes (`process_day`, `_index.json` updates).
  - Cache-only: none.
- JSON writes
  - Non-cache-only: yes (`cf_report.json` by default).
- Rotation writes
  - In sync default output mode: current copied to previous and history.
- PDF writes
  - always writes requested output path.

## `cf-report sync` (exact flow)

```mermaid
flowchart TD
    A[cmd_sync] --> B[_parse_sync_types]
    B --> C[validate_and_build_sync_options]
    C --> D[load_app_config + resolve_zone_filter]
    D --> E[run_sync]
    E --> F[cache_lock]
    F --> G[_run_sync_locked]
    G --> H{default_output_mode}
    H -- yes --> I[_rotate_report_outputs]
    H -- no --> J[skip rotation]
    I --> K[get_zone per zone]
    J --> K
    K --> L[_sync_days_for_mode]
    L --> M[process_day zone/day/stream]
    M --> N[save_zone_index merge bounds]
    N --> O[_report_bounds_from_indices]
    O --> P[collect_days_payloads read cache]
    P --> Q[append_live_today if include_today]
    Q --> R[fetch_zone_health skip option aware]
    R --> S[select_previous_report_for_period]
    S --> T[build_executive_summary]
    T --> U[build_report + write JSON/stdout]
```

### `process_day` decision tree

- Outside retention -> write envelope `_source="null"` (no API call).
- Cache exists and not refresh and not error -> skip.
- Otherwise call fetcher API:
  - success -> `_source="api"`
  - rate limit -> `_source="error"` + retry-after
  - other API error -> `_source="error"`

## Stream-to-API mapping

- `dns`: GraphQL `dnsAnalyticsAdaptiveGroups`
- `http`: GraphQL `httpRequests1dGroups`
- `http_adaptive`: GraphQL `httpRequestsAdaptiveGroups`
- `security`: GraphQL `httpRequestsAdaptiveGroups`
- `cache`: GraphQL `httpRequestsAdaptiveGroups`
- `dns_records`: REST DNS records
- `audit`: REST account audit logs
- `certificates`: REST certificate packs

Registry order (`FETCHER_REGISTRY`) defines sync iteration and default `--types`.

## Baseline selection for comparisons

Function: `select_previous_report_for_period(...)`

Candidate set:

- `cf_report.previous.json`
- `outputs/history/cf_report_*.json`

Filter gates:

- parseable report period
- strict chronology (`candidate.end < current.start`)
- not same exact period
- same zone exists in candidate
- semantic mode: exact expected baseline bounds
- other modes: equal period length

Best candidate:

- most recent valid `period.end`.

## `cf-report clean` flow

```mermaid
flowchart TD
    A[cmd_clean] --> B[scope validation]
    B --> C{all and no force}
    C -- yes --> X[invalid params]
    C -- no --> D[run_clean]
    D --> E[cache_lock]
    E --> F{older_than provided}
    F -- no --> G[delete selected cache/history roots]
    F -- yes --> H[cutoff date]
    H --> I[prune cache day dirs]
    H --> J[prune history files]
```

No Cloudflare API calls in clean.

## `cf-report zones` commands

```mermaid
flowchart TD
    A[zones subcommands] --> B{subcommand}
    B -- list --> C[load_config + CloudflareClient]
    C --> D[list_all_zones]
    D --> E[print]
    B -- add --> F[load_config]
    F --> G{--id xor --name}
    G -- id --> H[get_zone]
    G -- name --> I[find_zone_by_name]
    H --> J[dedupe + save_config]
    I --> J
    B -- remove --> K[load_config]
    K --> L[remove matching zone]
    L --> M[save_config]
```

## `cf-report init` flow

```mermaid
flowchart TD
    A[cmd_init] --> B[resolve config path]
    B --> C{exists}
    C -- yes --> X[error]
    C -- no --> D[prompt token]
    D --> E[template_config + set token]
    E --> F[save_config]
```
