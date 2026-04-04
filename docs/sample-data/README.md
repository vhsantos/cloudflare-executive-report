# Sample data (illustrative)

Fictional JSON for documentation. Uses **example.com** and the placeholder zone id from the config example in the main README. **No real customer data.**

## Layout

- **`cache/`** - Mirrors the on-disk layout under `cache_dir` (see main README). Paths match what **`cf-report sync`** writes: `{zone_id}/_index.json` and `{zone_id}/{YYYY-MM-DD}/{stream}.json`.
- **`report/`** - Interim **aggregated JSON** report (current CLI output). When PDF export lands, the **deliverable** output will be PDF; this folder documents the JSON shape until then.

## Files

| Path                                                                                                    | Role                                                                            |
| ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| [`cache/.../_index.json`](cache/a1b2c3d4e5f6789012345678abcdef01/_index.json)                           | Per-zone stream bounds (`earliest` / `latest`).                                 |
| [`cache/.../2026-04-01/dns.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-04-01/dns.json)           | One day, DNS envelope (`_source: api`).                                         |
| [`cache/.../2026-04-01/http.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-04-01/http.json)         | Same day, HTTP envelope.                                                        |
| [`cache/.../2026-04-01/security.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-04-01/security.json) | Same day, security envelope.                                                    |
| [`cache/.../2026-03-15/dns.json`](cache/a1b2c3d4e5f6789012345678abcdef01/2026-03-15/dns.json)           | Day **outside** the index window - `_source: "null"` (retention / not fetched). |
| [`report/report-sample.json`](report/report-sample.json)                                                | One-zone executive JSON (shape of `cf-report sync` **`-o`** output today).      |

See the main [README](../../README.md) for retention, CLI, and cache layout.
