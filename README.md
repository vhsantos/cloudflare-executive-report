# cloudflare-executive-report

Python CLI (**`cf-report`**) for the Cloudflare Executive Report - multi-zone reporting, on-disk cache, JSON output, and zone/config commands. All dates and report periods are **UTC**.

## Requirements

- Python 3.11+
- Cloudflare API token with at least **Zone:Read** and **Analytics:Read** (wording in the dashboard may be **Zone → Read** and **Analytics → Read** under the appropriate resource groups).

See [Cloudflare API token permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/) and match the labels shown when you create the token.

## Install

```bash
pip install -e ".[dev]"
```

Entry point: `cf-report`

## Configuration

Default path: `~/.cf-report/config.yaml` (Windows: `%USERPROFILE%\.cf-report\config.yaml`).

Example:

```yaml
api_token: "cfat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
cache_dir: "~/.cache/cf-report"
default_zone: "example.com"
log_level: "info"

zones:
  - id: "4b9bc3686111ec5463800e71aca76e1a"
    name: "example.com"
```

## DNS analytics retention

Historical DNS analytics depend on the zone plan (approximate):

| Plan       | DNS retention (typical) |
|-----------|-------------------------|
| Free      | 7 days                  |
| Pro+      | 31 days                 |
| Enterprise| 62 days                 |

The tool maps retention from the zone’s plan returned by the Cloudflare API. Dates outside retention are stored in cache as `_source: "null"` **without** calling the API (unless you use `--refresh`, which still cannot retrieve data older than Cloudflare retains).

## Cache layout

Under `cache_dir` (default `~/.cache/cf-report`):

```text
{cache_dir}/
├── .lock
└── {zone_id}/
    ├── _index.json
    └── {YYYY-MM-DD}/
        └── dns.json
```

Concurrent runs use `.lock`; if the lock is still held after **30 seconds**, the process exits with code **5**.

## CLI behavior

- **`cf-report sync`** - **Incremental:** fills missing UTC days from `dns.latest + 1` through **yesterday** (see `_index.json`). On a brand-new cache, `latest` is treated as yesterday, so the first incremental run does **not** backfill history; use `--last` or `--start`/`--end` for that.
- **`cf-report sync --last 7`** - Fetches the last **7** complete UTC days (through yesterday); **always** refetches those days (ignores cache for that window).
- **`cf-report sync --last`** - Error: number is required (`Error: --last requires a number. Example: --last 7`).
- **`cf-report sync --start YYYY-MM-DD --end YYYY-MM-DD`** - Both flags required together; same "always fetch" behavior for that inclusive range. `--end` must not be after yesterday unless you use **`--include-today`**.
- **`cf-report sync --refresh`** - For the active range, ignore cache and refetch (including days previously `_source: "null"` where the API might now return data).
- **`cf-report sync --include-today`** - Includes today in the report; today is **not** written to `dns.json` (incomplete day).
- **`cf-report sync --output PATH`** - Write JSON report (default: `./cf_report_output.json`).
- **`cf-report sync --zone NAME_OR_ID`** - Single zone from config.
- **`cf-report sync --types dns`** - Default; other type values are ignored.

Other commands: `cf-report init`, `cf-report zones list|add|remove`, `cf-report clean --older-than N` or `clean --all`.

## Logging

- **`--verbose`** - Debug logging (timing, `cf-ray` / `cf-request-id` when present, truncated error bodies).
- **`--quiet`** - Suppresses progress lines; errors still go to stderr.

## Exit codes

| Code | Meaning                          |
|------|----------------------------------|
| 0    | Success                          |
| 1    | General error                    |
| 2    | Invalid parameters               |
| 3    | Authentication failed (401/403)  |
| 4    | Rate limit exceeded after retries|
| 5    | Cache lock timeout               |

## Development

```bash
ruff check src tests
ruff format src tests
pytest
```

## Scope

This tool collects **DNS** metrics via GraphQL `dnsAnalyticsAdaptiveGroups`.
