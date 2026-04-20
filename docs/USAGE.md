# Usage Guide

Practical reference for running `cf-report` and configuring `config.yaml`.

## Why this exists

This page answers two questions quickly:

- Which commands should I run for common workflows?
- Which config fields control behavior in production and CI?

## Quick start (30 seconds)

```bash
pip install cloudflare-executive-report
cf-report init
cf-report sync --last 30
cf-report report -o security-report.pdf
```

You now have a local cache plus your first PDF report.

## Command cheatsheet

| Command            | What it does                                             |
| ------------------ | -------------------------------------------------------- |
| `cf-report init`   | Create a template config file (interactive token prompt) |
| `cf-report sync`   | Fetch Cloudflare data and write cache only               |
| `cf-report report` | Generate PDF from cache (syncs first if needed).         |
| `cf-report clean`  | Clean cache/history files                                |
| `cf-report zones`  | Add/remove/list zones in config                          |

> Note: `cf-report report` auto-includes `http_adaptive` metrics for executive reliability KPIs.

## Common command patterns

```bash
# Executive profile for last 30 complete days
cf-report report -o exec.pdf --last 30

# Detailed profile and SVG charts
cf-report report -o detailed.pdf --last 14 --types dns,http,security,cache,http_adaptive,dns_records,audit,certificates

# Cache-only reproducible report
cf-report report -o offline.pdf --cache-only --start 2026-04-01 --end 2026-04-14

# One zone only
cf-report report -o zone.pdf --zone example.com --last 30
```

## Complete config example

```yaml
api_token: "cfat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
cache_dir: "~/.cf-report/cache"
history_dir: "~/.cf-report/history"
default_zone: ""
log_level: "info"
default_period: "last_month"
types:
  - dns
  - http
  - security
  - cache
  - http_adaptive
  - dns_records
  - audit
  - certificates

zones:
  - id: "023e105f4ecef8ad9ca31a8372d0c353"
    name: "example.com"

pdf:
  image_quality: "medium" # low | medium | high
  chart_format: "png" # png | svg
  map_format: "png" # png | svg
  profile: "executive" # minimal | executive | detailed
  colors:
    primary: "#2563eb"
    accent: "#f38020"

executive:
  disabled_rules: []
  include_appendix: true
  reference_risk_weight: 60
  verdict_warn_threshold: 3

email:
  enabled: false
  smtp_host: "smtp.example.com"
  smtp_port: 587
  smtp_ssl: false
  smtp_starttls: true
  smtp_user: "reports@example.com"
  smtp_password: ""
  smtp_from: "reports@example.com"
  recipients:
    - "security@example.com"
  subject: "Cloudflare Executive Report - {date}"
  body: |
    Hello,

    Attached is the Cloudflare Executive Report for {period} ({zone_count} zone(s)).

    Regards,
    Cloudflare Report Tool

portfolio:
  sort_by: "score" # score | zone_name

cover:
  enabled: true
  company_name: "Example Inc"
  logo_path: ""
  title: "Cloudflare Executive Report"
  subtitle: "Security & Performance Overview"
  notes: ""
  prepared_for: ""
  classification: ""
  date_format: "%d/%b/%Y"
```

## Config field reference

### Secrets and precedence

For both `api_token` and `email.smtp_password`:

```txt
config value > environment variable > empty string
```

`api_token` environment variables (used only if config is empty):

- `CF_REPORT_API_TOKEN` (preferred)
- `CLOUDFLARE_API_TOKEN` (fallback)

`smtp_password` environment variable (used only if config is empty):

- `CF_REPORT_SMTP_PASSWORD`

### Root fields

- `api_token` (`str`) - Cloudflare API token.
- `cache_dir` (`str`) - local cache root.
- `history_dir` (`str`) - output root (`history/cf_report.json`, history, and default PDFs).
- `default_zone` (`str`) - used when `--zone` is omitted.
- `log_level` (`str`) - typical values: `debug`, `info`, `warning`, `error`.
- `default_period` (`str`) - default period preset used when no period flags are provided. Supported values: `incremental`, `yesterday`, `last_week`, `this_week`, `last_month`, `this_month`, `last_year`, `this_year`, or `last_N` (example: `last_30`).
- `types` (`list[str]`) - default stream list for sync/report.
- `zones` (`list`) - each item requires `id` and `name`.

### `pdf`

- `image_quality`: `low | medium | high`
- `chart_format`: `png | svg`
- `map_format`: `png | svg`
- `profile`: `minimal | executive | detailed`
- `colors.primary`: hex color `#RRGGBB`
- `colors.accent`: hex color `#RRGGBB`

### `executive`

- `disabled_rules` (`list[str]`) - rule key patterns to suppress.
- `include_appendix` (`bool`) - include NIST/control appendix.
- `reference_risk_weight` (`int`) - denominator for posture score formula.
- `verdict_warn_threshold` (`int`) - warning count threshold used by verdict logic.

### `email`

- `enabled` (`bool`) - enables SMTP sending when `cf-report report --email` is used.
- `smtp_host` (`str`) - SMTP server host.
- `smtp_port` (`int`) - SMTP port (`587` default).
- `smtp_ssl` (`bool`) - implicit TLS mode.
- `smtp_starttls` (`bool`) - STARTTLS mode.
- `smtp_user` (`str`) - SMTP username.
- `smtp_password` (`str`) - SMTP password.
- `smtp_from` (`str`) - sender email address.
- `recipients` (`list[str]`) - recipient list.
- `subject` (`str`) - supports placeholders like `{date}`.
- `body` (`str`) - supports placeholders like `{period}` and `{zone_count}`.

Important: `smtp_ssl` and `smtp_starttls` cannot both be `true`.

### `portfolio`

- `sort_by`: `score | zone_name`

### `cover`

- `enabled` (`bool`) - include cover page.
- `company_name` (`str`) - company text on cover.
- `logo_path` (`str`) - path to local image.
- `title` (`str`) - report title.
- `subtitle` (`str`) - report subtitle.
- `notes` (`str`) - optional free text.
- `prepared_for` (`str`) - recipient label.
- `classification` (`str`) - sensitivity marker (example: Internal).
- `date_format` (`str`) - Python `strftime` format string.

## Where to find more

- CI/CD patterns and headless examples: `docs/ci-cd.md`
- Developer internals: `docs/developers/`
- Demo assets and examples: `docs/examples/`, `docs/sample-data/`
