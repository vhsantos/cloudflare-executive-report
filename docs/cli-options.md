# CLI Options Reference

Source of truth: `src/cloudflare_executive_report/cli.py`.

## Global options (all commands)

| Option            | Type | Default | Description                                          |
| ----------------- | ---- | ------- | ---------------------------------------------------- |
| `--verbose`, `-v` | bool | `False` | Debug logging for this run (overrides config level). |
| `--quiet`, `-q`   | bool | `False` | Suppress progress output (errors still shown).       |

## `cf-report init`

| Option     | Type | Default | Description                |
| ---------- | ---- | ------- | -------------------------- |
| `--config` | path | `None`  | Override config file path. |

## `cf-report report`

| Option               | Type      | Default               | Description                                                             |
| -------------------- | --------- | --------------------- | ----------------------------------------------------------------------- |
| `--last`             | int       | `None`                | Last N complete UTC days.                                               |
| `--start`            | str       | `None`                | Start date `YYYY-MM-DD` (requires `--end`).                             |
| `--end`              | str       | `None`                | End date `YYYY-MM-DD` (requires `--start`).                             |
| `--last-month`       | bool      | `False`               | Use previous full UTC month.                                            |
| `--last-week`        | bool      | `False`               | Use previous full UTC week.                                             |
| `--last-year`        | bool      | `False`               | Use previous full UTC year.                                             |
| `--this-month`       | bool      | `False`               | Use current UTC month to date.                                          |
| `--this-week`        | bool      | `False`               | Use current UTC week to date.                                           |
| `--this-year`        | bool      | `False`               | Use current UTC year to date.                                           |
| `--yesterday`        | bool      | `False`               | Use previous UTC day.                                                   |
| `--refresh`          | bool      | `False`               | Ignore cache and re-fetch active range during sync step.                |
| `--include-today`    | bool      | `False`               | Include today in the report end date.                                   |
| `--cache-only`       | bool      | `False`               | Skip sync and build PDF from cache only.                                |
| `--refresh-health`   | bool      | `False`               | Refresh live zone health for this report window and rebuild report JSON |
| `--output`, `-o`     | path      | `None`                | Output PDF path (required for `report`).                                |
| `--zone`             | str       | `None`                | Zone id or name; if omitted, uses default zone or all configured zones. |
| `--types`            | str (csv) | `default_types_csv()` | Comma-separated stream ids. Include `http_adaptive` for executive error/latency KPIs. |
| `--top`              | int       | `10`                  | Top-N size for ranked lists.                                            |
| `--skip-zone-health` | bool      | `False`               | Omit zone health REST fetch.                                            |
| `--output-dir`       | path      | `None`                | Override JSON/history output root for this run.                         |
| `--config`           | path      | `None`                | Override config path.                                                   |

## `cf-report sync`

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--last` | int | `None` | Last N complete UTC days. |
| `--start` | str | `None` | Start date `YYYY-MM-DD` (requires `--end`). |
| `--end` | str | `None` | End date `YYYY-MM-DD` (requires `--start`). |
| `--last-month` | bool | `False` | Use previous full UTC month. |
| `--last-week` | bool | `False` | Use previous full UTC week. |
| `--last-year` | bool | `False` | Use previous full UTC year. |
| `--this-month` | bool | `False` | Use current UTC month to date. |
| `--this-week` | bool | `False` | Use current UTC week to date. |
| `--this-year` | bool | `False` | Use current UTC year to date. |
| `--yesterday` | bool | `False` | Use previous UTC day. |
| `--refresh` | bool | `False` | Ignore cache and re-fetch active range. |
| `--include-today` | bool | `False` | Include today (possibly incomplete data). |
| `--output`, `-o` | path | `None` | Not supported (`sync` is data-only). |
| `--zone` | str | `None` | Zone id or name; if omitted, uses default zone when set. |
| `--types` | str (csv) | `default_types_csv()` | Comma-separated stream ids. Include `http_adaptive` for executive error/latency KPIs. |
| `--top` | int | `10` | Top-N size for ranked lists. |
| `--skip-zone-health` | bool | `False` | Omit zone health REST fetch. |
| `--output-dir` | path | `None` | Override JSON/history output root for this run. |
| `--config` | path | `None` | Override config path. |

## `cf-report clean`

| Option         | Type | Default | Description                                      |
| -------------- | ---- | ------- | ------------------------------------------------ |
| `--older-than` | int  | `None`  | Delete selected scope entries older than N days. |
| `--cache`      | bool | `False` | Clean cache scope.                               |
| `--history`    | bool | `False` | Clean report history scope.                      |
| `--all`        | bool | `False` | Clean both cache and history.                    |
| `--force`      | bool | `False` | Confirm destructive cleanup for `--all`.         |
| `--output-dir` | path | `None`  | Override JSON/history output root for this run.  |

## `cf-report zones list`

No command-specific options (global `--verbose/--quiet` still apply).

## `cf-report zones add`

| Option   | Type | Default | Description           |
| -------- | ---- | ------- | --------------------- |
| `--id`   | str  | `None`  | Zone ID.              |
| `--name` | str  | `None`  | Zone name (hostname). |

Notes:

- Exactly one of `--id` or `--name` must be provided.

## Metadata and Period Resolution Notes

- `sync` and `report` share period/type resolution logic via `src/cloudflare_executive_report/common/period_resolver.py`.
- Output report JSON now includes:
  - `report_type`
  - `data_fingerprint`
  - `zone_health_fetched_at`

## `cf-report zones remove`

| Option   | Type | Default | Description           |
| -------- | ---- | ------- | --------------------- |
| `--id`   | str  | `None`  | Zone ID.              |
| `--name` | str  | `None`  | Zone name (hostname). |

Notes:

- Exactly one of `--id` or `--name` must be provided.
