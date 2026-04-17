# Sample data (illustrative)

Fictional JSON for documentation examples. Uses `example.com` and a placeholder zone id. No real customer data.

## Layout

- `cache/` - mirrors the real on-disk cache layout under `cache_dir`:
  - `{zone_id}/_index.json`
  - `{zone_id}/{YYYY-MM-DD}/{stream}.json`
- `report/` - sample aggregated report snapshot JSON.

## Files

| Path                                                                                                    | Role                                            |
| ------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| [`cache/.../_index.json`](cache/a1b2c3d4e5f6789012345678abcdef01/_index.json)                           | Per-zone stream bounds (`earliest` / `latest`). |
| [`cache/.../2026-04-01/dns.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-04-01/dns.json)           | One day, DNS envelope (`_source: api`).         |
| [`cache/.../2026-04-01/http.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-04-01/http.json)         | One day, HTTP envelope.                         |
| [`cache/.../2026-04-01/security.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-04-01/security.json) | One day, security envelope.                     |
| [`cache/.../2026-03-15/dns.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-03-15/dns.json)           | Day outside index window (`_source: "null"`).   |
| [`report/report-sample.json`](report/report-sample.json)                                                | One-zone executive report snapshot example.     |

See [README](../../README.md) and [USAGE](../USAGE.md) for CLI behavior and configuration.
