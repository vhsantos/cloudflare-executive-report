# Cloudflare Executive Report

Turn Cloudflare analytics into executive-ready PDF reports with security scores, NIST mappings, and multi-zone portfolio views.

[![PyPI version](https://img.shields.io/pypi/v/cloudflare-executive-report)](https://pypi.org/project/cloudflare-executive-report/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Why this tool exists

Cloudflare dashboard data is excellent for day-to-day operations, but executive reporting often needs:

- historical windows beyond dashboard convenience
- one report across many zones
- reusable PDF outputs for leadership and audit trails
- concise risk scoring and action narrative

Cloudflare Executive Report fills that gap with local caching and deterministic report generation.

## What you get

| Feature              | Outcome                                                          |
| -------------------- | ---------------------------------------------------------------- |
| Historical cache     | Sync once, generate reports later without re-querying everything |
| Multi-zone portfolio | One page for score, grade, and common risks across zones         |
| Executive summary    | Verdict, KPIs, takeaways, and actions per zone                   |
| Security score       | 0-100 + grade, based on risk takeaways only                      |
| NIST mapping         | Control references for compliance context                        |
| Email delivery       | Optional SMTP send after successful PDF generation               |
| Brand colors         | Primary/accent customization in PDF                              |

## Install

```bash
pip install cloudflare-executive-report
```

Optional SVG rendering:

```bash
pip install "cloudflare-executive-report[svg]"
```

## API token permissions (read-only)

Create token in Cloudflare Dashboard: **My Profile -> API Tokens**.

### Required

| Permission (Zone) | Purpose                                   |
| ----------------- | ----------------------------------------- |
| Zone Read         | Zone metadata and zone management helpers |
| Analytics Read    | DNS/HTTP/security/cache GraphQL analytics |

### Required for zone health (default report behavior)

| Permission (Zone)      | Purpose                          |
| ---------------------- | -------------------------------- |
| Zone Settings Read     | SSL/HTTPS/security/DDOS settings |
| DNS Read               | DNSSEC status                    |
| Firewall Services Read | Active firewall rule counts      |

If zone-health permissions are missing, those fields become `unavailable` with warnings. Use `--skip-zone-health` to disable zone-health fetch.

## Quick start

```bash
cf-report init
cf-report sync --last 30
cf-report report -o security-report.pdf
```

This initializes config, syncs 30 days of data, and generates a PDF report.
Add `--email` to the report command to send it via SMTP when email is enabled in config.

## Configuration

Default file: `~/.cf-report/config.yaml`.

```yaml
api_token: "cfat_xxx"
cache_dir: "~/.cache/cf-report"
output_dir: "~/.cf-report"
log_level: "info"

zones:
  - id: "abc123..."
    name: "example.com"

pdf:
  profile: "executive"     # minimal | executive | detailed
  chart_format: "png"      # png | svg
  map_format: "png"        # png | svg
  colors:
    primary: "#2563eb"
    accent: "#f38020"

executive:
  disabled_rules:
    - dnssec
    - security_.*
  include_appendix: true
  reference_risk_weight: 60
  verdict_warn_threshold: 3

email:
  enabled: false
  smtp_host: "smtp.example.com"
  smtp_port: 587
  smtp_starttls: true
  smtp_user: "reports@example.com"
  smtp_password: "..."
  recipients:
    - "security@example.com"
```

## Report profiles

| Profile     | Cover | Portfolio (2+ zones) | Zone summary | Stream details | Best for             |
| ----------- | ----- | -------------------- | ------------ | -------------- | -------------------- |
| `minimal`   | Yes   | Yes                  | No           | No             | quick status         |
| `executive` | Yes   | Yes                  | Yes          | No             | leadership (default) |
| `detailed`  | Yes   | Yes                  | Yes          | Yes            | technical deep dive  |

## PDF examples (demo data)

The repository includes sample PDFs generated from synthetic placeholder zones:

- [Minimal profile](docs/examples/report-minimal-png-medium.pdf) - compact portfolio-focused output (`png`, medium quality).
- [Executive profile](docs/examples/report-executive-png-medium.pdf) - leadership summary with score, takeaways, and actions (`png`, medium quality).
- [Detailed profile](docs/examples/report-detailed-png-medium.pdf) - full stream pages for DNS, HTTP, Security, and Cache (`png`, medium quality).
- [Detailed SVG (single page)](docs/examples/report-detailed-svg-high-single-page.pdf) - one extracted page rendered with SVG/high quality for visual comparison.

Note: SVG/high-quality rendering can increase PDF size significantly compared to `png` medium quality.

## Security score model

Only `risk` takeaways in `risks` section affect score.
`win`, `action`, `comparison`, and `observation` are informational for scoring.

```text
score = max(0, 100 - (total_risk_weight / 60) * 100)
```

Examples:

| Total risk weight | Score | Grade |
| ----------------- | ----- | ----- |
| 0                 | 100   | A+    |
| 19                | 68.3  | C+    |
| 26                | 56.7  | C     |
| 60+               | 0     | F     |

Example composition: `SSL off (10) + WAF disabled (9) = 19`, which maps to score `68.3` (`C+`).

## Data quality notes

Some metrics are trend-oriented approximations:

- top entities are merged from daily top lists
- mitigation/security analytics can be sampled
- relative trends are more reliable than single-point absolutes

Use this report as executive posture guidance, not packet-level forensic truth.

## Retention behavior

Plan-aware windows currently enforced by this tool:

| Plan       | DNS | Security | HTTP |
| ---------- | --- | -------- | ---- |
| Free       | 7d  | 7d       | 30d  |
| Pro        | 31d | 7d       | 30d  |
| Business   | 31d | 31d      | 30d  |
| Enterprise | 62d | 90d      | 30d  |

Days outside these windows are cached as `unavailable` and skipped from API calls.

## CLI overview

### Sync

```bash
cf-report sync --last 30
cf-report sync --start 2026-01-01 --end 2026-03-31
cf-report sync --zone example.com --last 30
cf-report sync --last 7 --refresh
```

### Report

```bash
cf-report report -o report.pdf
cf-report report -o report.pdf --email
cf-report report -o report.pdf --cache-only
cf-report report -o report.pdf --skip-zone-health
```

### Zones and cache cleanup

```bash
cf-report zones list
cf-report zones add --id abc123 --name example.com
cf-report zones remove --name example.com
cf-report clean --older-than 90
cf-report clean --all
```

## Exit codes

| Code | Meaning               |
| ---- | --------------------- |
| 0    | Success               |
| 1    | General error         |
| 2    | Invalid parameters    |
| 3    | Authentication failed |
| 4    | Rate limit exceeded   |
| 5    | Cache lock timeout    |

## Contributing

Developer setup and architecture notes: [CONTRIBUTING.md](CONTRIBUTING.md).

## Links

- [PyPI](https://pypi.org/project/cloudflare-executive-report/)
- [GitHub](https://github.com/vhsantos/cloudflare-executive-report)
- [Issues](https://github.com/vhsantos/cloudflare-executive-report/issues)

## License

MIT. See [LICENSE](LICENSE).
