# cloudflare-executive-report

Python CLI (**`cf-report`**) that pulls Cloudflare **DNS**, **HTTP**, **security**, and **cache** analytics, optional **zone health** (REST), caches daily payloads on disk, and writes a JSON report plus PDF. All dates are **UTC**.

## Requirements

- **Python 3.11+**
- **API token** - in the dashboard (**My Profile → API Tokens → Create Token**), under **Permissions**, add the **Zone** permission groups below (official names from [API token permissions](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)). Set **Zone Resources** to the same zones you list in config (or all zones on the account, if you use that).

### Always needed (sync + report)

| Permission (Zone)  | Used for                                                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **Zone Read**      | `zones.get` / `zones.list` - zone metadata (including `plan` for retention) and `cf-report zones`.                         |
| **Analytics Read** | [GraphQL Analytics API](https://developers.cloudflare.com/analytics/graphql-api/) - DNS, HTTP, and firewall event queries. |

### Also needed for zone health (default)

Zone health is extra REST calls on each report. Without these, matching fields are `unavailable` and a warning is logged; use **`--skip-zone-health`** to omit zone health entirely.

| Permission (Zone)          | Used for                                                                          |
| -------------------------- | --------------------------------------------------------------------------------- |
| **Zone Settings Read**     | Per-setting reads (`ssl`, `always_use_https`, `security_level`, `advanced_ddos`). |
| **DNS Read**               | DNSSEC status (`dns.dnssec`).                                                     |
| **Firewall Services Read** | Count of active (unpaused) firewall rules (`firewall.rules`).                     |

**Write** permissions are not required. If Cloudflare adds or renames permission groups, use the live list from the doc above or the [List permission groups](https://developers.cloudflare.com/api/resources/user/subresources/tokens/subresources/permission_groups/methods/list/) API.

## Install

In the project directory (after cloning or unpacking the sources):

```bash
pip install .
```

This installs the **`cf-report`** command on your `PATH`.

## Configuration

Default file: **`~/.cf-report/config.yaml`** (Windows: `%USERPROFILE%\.cf-report\config.yaml`).

Example:

```yaml
api_token: "cfat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
cache_dir: "~/.cache/cf-report"
output_dir: "~/.cf-report"
default_zone: "" # optional: used when `sync` is run without `--zone`
log_level: "info" # e.g. debug, warning (same idea as verbose for logging)
default_period: "last_month" # reserved for future default period selection
types: [] # optional default stream ids

zones:
  - id: "a1b2c3d4e5f6789012345678abcdef01"
    name: "example.com"

pdf:
  image_quality: "medium" # low | medium | high
  chart_format: "png" # png | svg (time-series charts and table charts)
  map_format: "png" # png | svg (world maps)
  profile: "executive" # minimal | executive | detailed (report length; cover still uses cover.enabled)

executive:
  disabled_rules:
    - review_dnssec
    - hsts_suboptimal
    - security_.*
  include_nist_appendix: true
  reference_risk_weight: 60
  verdict_warn_threshold: 3

email:
  enabled: false
  smtp_host: ""
  smtp_port: 587
  smtp_ssl: false # true for SMTPS (e.g. port 465); cannot combine with smtp_starttls
  smtp_starttls: true # upgrade plain SMTP with STARTTLS (typical on port 587)
  smtp_user: ""
  smtp_password: ""
  smtp_from: "" # optional display; defaults to smtp_user
  recipients: []
  subject: 'Cloudflare Executive Report - {{date}}' # {{period}}, {{zone_count}}
  body: |
    Hello,

    Attached is the Cloudflare Executive Report for {{period}} ({{zone_count}} zone(s)).

    Regards,
    Cloudflare Report Tool

portfolio:
  sort_by: "score" # score | zone_name

cover:
  enabled: true
  company_name: ""
  logo_path: ""
  title: "Cloudflare Executive Report"
  subtitle: "Security & Performance Overview"
  notes: ""
  prepared_for: ""
  classification: ""
  date_format: "%d/%b/%Y"
```

- **`default_zone`**: If set and you omit **`--zone`** on **`sync`**, only that zone (by id or name) is processed; if empty, all configured zones run.
- **`output_dir`**: Root for JSON outputs/history used by `sync` and `report` (default `~/.cf-report`).
- **`pdf.image_quality`**: Raster DPI preset (`low|medium|high`) for PNG charts/maps.
- **`pdf.chart_format`**: Chart format (`png|svg`), default `png`.
- **`pdf.map_format`**: World map format (`png|svg`), default `png` (recommended for smaller PDFs).
- **`pdf.profile`**: Report length preset: `minimal` (cover if enabled, multi-zone portfolio when 2+ zones, no per-zone executive or stream sections), `executive` (default, adds per-zone executive summary, no stream sections), `detailed` (full report with stream sections for the streams you configure). Cover still follows `cover.enabled`.
- **`executive.disabled_rules`**: Remove executive rules by phrase key or regex (affects text and score).
- **`portfolio.sort_by`**: Multi-zone portfolio ordering (`score` or `zone_name`).
- **`email`**: Optional SMTP. Set **`enabled: true`**, fill **`smtp_host`**, **`recipients`**, and **`smtp_user`** (or **`smtp_from`**). After `cf-report report -o out.pdf`, add **`--email`** to send that PDF. Templates support **`{{date}}`**, **`{{period}}`**, **`{{zone_count}}`**.
- **SVG dependency**: If using `pdf.chart_format: svg` or `pdf.map_format: svg`, install optional dependency:
  - `pip install '.[svg]'`

## What gets collected

| Piece         | Source                                                  | Cached per day                |
| ------------- | ------------------------------------------------------- | ----------------------------- |
| DNS           | GraphQL `dnsAnalyticsAdaptiveGroups`                    | `dns.json`                    |
| HTTP (daily)  | GraphQL `httpRequests1dGroups`                          | `http.json`                   |
| HTTP adaptive | GraphQL `httpRequestsAdaptiveGroups` (status + latency) | `http_adaptive.json`          |
| Security      | GraphQL `httpRequestsAdaptiveGroups` (security-focused) | `security.json`               |
| Cache         | GraphQL `httpRequestsAdaptiveGroups` (cache-focused)    | `cache.json`                  |
| DNS records   | SDK (`dns.records.list`, snapshot)                      | `dns_records.json`            |
| Audit logs    | SDK (`audit_logs.list`, snapshot)                       | `audit.json`                  |
| Certificates  | SDK (`ssl.certificate_packs.list`, snapshot)            | `certificates.json`           |
| Zone health   | REST (settings, DNSSEC, firewall rules)                 | Not cached (live each report) |

## Executive summary (v1)

Each zone in `cf_report_output.json` includes `executive_summary`, derived from synced rollups plus live `zone_health`: `dns`, `http`, `http_adaptive`, `security`, `cache`, `dns_records`, `audit`, `certificates`, and `zone_health`.

- Core fields include `verdict`, `verdict_reasons`, `kpis`, `takeaways`, and `actions` (up to five).
- The same shared builder (`build_executive_summary`) is used by both JSON sync output and PDF rendering.
- Reliability wording for adaptive HTTP uses shared thresholds in `executive/constants.py`.
- If you narrow `--types` on `sync` or `report`, include `http_adaptive` when executive
  error/latency KPIs are required.
- Executive security wording is business-facing:
  - `Blocked/Challenged`
  - `Mitigation rate`

### Security posture score (0-100)

The JSON `executive_summary` includes a **security score** so you can track one number over time (the PDF first-row KPI uses the label **Score** with a compact value like **72 C+**). It reflects **risks only** (bad posture lines in the **`risks`** takeaway bucket). **Wins**, period **comparisons** (`deltas`), and **correlations** (`signals`) do **not** change the score.

- **Weights**: Each risk phrase uses its **`weight`** from `executive/phrase_catalog.py` (`RULE_CATALOG`, typically **1-10**). Unknown keys default to weight **5**.
- **Formula**: `score = round(max(0, 100 - (total_risk_weight / REF * 100)), 1)` where **`REF`** is **`SECURITY_POSTURE_REFERENCE_RISK_WEIGHT`** (default **60** in `common/constants.py`). **No risks** means **100** (perfect). Risk weight **60** or more maps to **0** (then stays **0** if weight is higher).
- **Letter grade** (from numeric score): **A+** >= 95, **A** >= 85, **B** >= 75, **C+** >= 65, **C** >= 55, **D+** >= 45, **D** >= 35, **F** below 35.
- **JSON fields**: Top-level **`security_score`** and **`security_grade`**, plus **`kpis.security_posture`** with **`score`**, **`grade`**, and **`risk_weight`** (summed risk weights).

**Example:** SSL off (10) + WAF off (9) = **19** risk weight, score **68.3** **C+**. This is a compact summary, not a full CSPM audit.

PDF reports render this executive summary first (per zone) before stream detail pages.

Analytics from Cloudflare may use different aggregation windows than raw logs; totals and rankings are approximate and may differ slightly from the dashboard.

## Retention (UTC calendar days)

**DNS** and **security** windows follow the zone **plan** (`plan.legacy_id` from the API), using the same tier grid:

| Plan (legacy_id) | Typical window |
| ---------------- | -------------- |
| Free (default)   | 7 days         |
| Pro / Business   | 31 days        |
| Enterprise       | 62 days        |

**HTTP** daily groups: **30 days** (same for all plans in this tool).

Days outside retention are stored as **`_source: "null"`** in cache without calling the API.

## Cache layout

Under **`cache_dir`** (from config):

```text
{cache_dir}/
├── .lock
└── {zone_id}/
    ├── _index.json
    └── {YYYY-MM-DD}/
        ├── dns.json
        ├── http.json
        └── security.json
```

**`_index.json`** stores per-stream `earliest` / `latest` dates for incremental sync.

Concurrent runs use **`.lock`**; if it is still held after **30 seconds**, exit code **5**.

**`--include-today`**: Extends the **report** through today's UTC date and merges **live** partial-day API data into the JSON output. **Today is not written** as a `YYYY-MM-DD/*.json` day file.

Illustrative cache layout and interim JSON report: **[docs/sample-data/](docs/sample-data/)**.

## CLI

### `cf-report sync`

- *(default)*: **Incremental** fetch of missing UTC days through **yesterday** (uses cache unless missing/error).
- `--last N`: restrict work to last **N** complete UTC days (still uses cache unless `--refresh`).
- `--start` / `--end`: fixed inclusive date range; `--end` cannot be after yesterday unless `--include-today`.
- `--refresh`: refetch active window (ignore good cache).
- `--include-today`: include today in report (live API; not cached as day file).
- `--output` / `-o`: report path (default `./cf_report_output.json`).
- `--zone`: one zone id/name from config; if omitted, uses `default_zone` when set.
- `--types`: comma-separated streams: `dns`, `http`, `http_adaptive`, `security`, `cache`, `dns_records`, `audit`, `certificates` (default all registered). Include `http_adaptive` for executive error/latency KPIs.
- `--top N`: ranked-list length (default 10).
- `--skip-zone-health`: omit zone health REST calls.

Global: **`--verbose` / `-v`** (debug for this run), **`--quiet` / -q** (errors only). Config **`log_level`** applies when not overridden.

First run with an empty cache: incremental sync does **not** backfill old history; use **`--last N`** or **`--start`/`--end`** once to seed days.

### Other commands

- **`cf-report init`** - create config template and prompt for token.
- **`cf-report zones list|add|remove`** - manage zones in config.
- **`cf-report clean --older-than N`** or **`--all`** - prune or wipe cache.

## Exit codes

| Code | Meaning                           |
| ---- | --------------------------------- |
| 0    | Success                           |
| 1    | General error                     |
| 2    | Invalid parameters                |
| 3    | Authentication failed             |
| 4    | Rate limit exceeded after retries |
| 5    | Cache lock timeout                |

## Contributing

Developer setup, tests, and how to add a new analytics stream: **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## License / scope

This project is a CLI for cache sync and **PDF analytics reports** (`cf-report report`); it does not ship email.
