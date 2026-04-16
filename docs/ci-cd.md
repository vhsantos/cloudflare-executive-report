# CI/CD Guide (Headless Runs)

Running `cf-report` in CI/CD is different from local execution. The `init` command is interactive, and sensitive credentials should never be stored in config files. This guide shows you how to:

- Provide API tokens and SMTP passwords via environment variables
- Persist cache between runs to avoid re-fetching data
- Generate reports automatically on schedules or commits

This document explains how to run `cf-report` in CI/CD and how to persist cache and history between runs.

## Core ideas

### 1) Secrets should be environment variables

Treat these as secrets:

- Cloudflare API token: `CF_REPORT_API_TOKEN` (preferred)
- SMTP password: `CF_REPORT_SMTP_PASSWORD`

The tool supports environment variables for these sensitive values.

### Supported environment variables (and precedence)

| Variable | Purpose | Notes |
| --- | --- | --- |
| `CF_REPORT_API_TOKEN` | Cloudflare API token | Preferred name |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token | Fallback name |
| `CF_REPORT_SMTP_PASSWORD` | SMTP password | Preferred name |

Notes:

- If both `CF_REPORT_API_TOKEN` and `CLOUDFLARE_API_TOKEN` are set, the tool uses `CF_REPORT_API_TOKEN`.

Precedence rule:

```txt
config value > environment variable > empty string
```

### 2) The config file is not a secret

The config file usually contains non-secret settings:

- zones
- cache_dir and output_dir
- PDF profile/colors
- email recipients and SMTP host/user (non-secret)

In CI, do not store a token in the config file. Prefer environment secrets.

### 3) Do not run `cf-report init` in CI

`cf-report init` is interactive (it prompts for the API token). In CI, provide:

- a config file via `--config`
- the token via `CF_REPORT_API_TOKEN`

### 4) Persist both cache and outputs for "history"

To reuse data between runs, persist:

- `cache_dir` (API day files)
- `output_dir/outputs` (snapshots and history)

If only `cache_dir` is persisted, sync runs will be faster, but report snapshots/history may be missing.

> Note: `--cache-only` reuse is strict (it must match the last snapshot fingerprint). Persisting `output_dir/outputs` helps baseline and comparison logic.

## Minimal CI approach

- Restore cache paths (if CI supports caching)
- Run `cf-report sync ...`
- Run `cf-report report ...`
- Upload the PDF as an artifact

## Split schedule pattern (recommended)

You can separate data collection and PDF generation into different jobs/workflows:

- Daily job: run `sync` only (keeps cache fresh)
- Monthly job: run `report` only (uses cached data)

This is useful when you want frequent cache refresh but only periodic executive PDFs.

### Example A: daily sync workflow (GitHub Actions)

```yaml
name: cf-report-sync-daily

on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install cloudflare-executive-report
      - run: printf "%s" "${{ vars.CF_REPORT_CONFIG_YAML }}" > .ci-config.yaml
      - run: cf-report sync --config .ci-config.yaml --last 30
        env:
          CF_REPORT_API_TOKEN: ${{ secrets.CF_REPORT_API_TOKEN }}
```

### Example B: monthly report workflow (GitHub Actions)

```yaml
name: cf-report-monthly-pdf

on:
  schedule:
    - cron: "0 6 1 * *"
  workflow_dispatch:

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install cloudflare-executive-report
      - run: printf "%s" "${{ vars.CF_REPORT_CONFIG_YAML }}" > .ci-config.yaml
      - run: cf-report report --config .ci-config.yaml --cache-only --last-month -o report-monthly.pdf
        env:
          CF_REPORT_API_TOKEN: ${{ secrets.CF_REPORT_API_TOKEN }}
      - uses: actions/upload-artifact@v4
        with:
          name: monthly-executive-report
          path: report-monthly.pdf
```

> Note: this split model requires persistent CI cache between runs. If `--cache-only` fails due to fingerprint mismatch, run a normal `sync` + `report` in the report workflow.

## Config as an environment variable

Some CI systems make it easier to store a whole YAML config as a secret or variable.
This pattern writes it to a file at runtime:

```bash
mkdir -p .ci
printf "%s" "$CF_REPORT_CONFIG_YAML" > .ci/config.yaml
```

> Security: if `CF_REPORT_CONFIG_YAML` contains secrets, treat it as a secret. Prefer putting only non-secret config in it and injecting secrets as env vars. Warning: never run `set -x` (or other verbose shell tracing) in CI steps that handle secrets. Commands and their arguments may be logged.

## Understanding `--cache-only`

The `--cache-only` flag generates a PDF without running sync. It reuses the most recent report snapshot, and the reuse check is strict.

The reuse fingerprint includes:

- date range
- zones included
- stream set (`--types`)
- `--top`
- `--include-today`

If any of these change (new zone, different date range, different `--types`), `--cache-only` can fail. For reliable CI runs, prefer running `sync` + `report` without `--cache-only`.

## GitHub Actions example (cache + artifact)

This example:

- uses `CF_REPORT_API_TOKEN` from GitHub Secrets
- writes config from a repository variable `CF_REPORT_CONFIG_YAML`
- caches both `cache_dir` and `output_dir/outputs`
- uploads the generated PDF

```yaml
name: cf-report

on:
  workflow_dispatch:
  schedule:
    - cron: "0 6 * * 1"

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install cloudflare-executive-report

      - name: Write config file
        env:
          CF_REPORT_CONFIG_YAML: ${{ vars.CF_REPORT_CONFIG_YAML }}
        run: |
          mkdir -p .ci
          printf "%s" "$CF_REPORT_CONFIG_YAML" > .ci/config.yaml

      - name: Restore cache
        uses: actions/cache@v4
        with:
          path: |
            .ci-cache/cf-report
            .ci-output/outputs
          key: cf-report-${{ runner.os }}-${{ github.ref_name }}
          restore-keys: |
            cf-report-${{ runner.os }}-${{ github.ref_name }}-
            cf-report-${{ runner.os }}-main-
            cf-report-${{ runner.os }}-

      - name: Run sync + report
        env:
          CF_REPORT_API_TOKEN: ${{ secrets.CF_REPORT_API_TOKEN }}
        run: |
          cf-report sync --config .ci/config.yaml --last 30
          cf-report report --config .ci/config.yaml --last 30 -o report.pdf

      - name: Upload PDF
        uses: actions/upload-artifact@v4
        with:
          name: cloudflare-executive-report
          path: report.pdf
```

### Required config values for this example

The config YAML should point to CI-friendly paths so caching works:

```yaml
api_token: ""
cache_dir: ".ci-cache/cf-report"
output_dir: ".ci-output"
zones:
  - id: "your-zone-id"
    name: "example.com"
pdf:
  profile: "executive"
```

Note: for GitHub, prefer repository Variables (not Secrets) for `CF_REPORT_CONFIG_YAML` if it contains no secrets.

## GitLab CI example (cache + artifact)

```yaml
stages: [report]

cf_report:
  image: python:3.12
  stage: report
  cache:
    key: "cf-report-${CI_COMMIT_REF_SLUG}"
    paths:
      - .ci-cache/cf-report/
      - .ci-output/outputs/
  script:
    - python -m pip install --upgrade pip
    - pip install cloudflare-executive-report
    - mkdir -p .ci
    - printf "%s" "$CF_REPORT_CONFIG_YAML" > .ci/config.yaml
    - cf-report sync --config .ci/config.yaml --last 30
    - cf-report report --config .ci/config.yaml --last 30 -o report.pdf
  artifacts:
    paths:
      - report.pdf
    expire_in: 30 days
  variables:
    PIP_DISABLE_PIP_VERSION_CHECK: "1"
    # Do not set secrets here. Set secrets in GitLab UI:
    # Settings -> CI/CD -> Variables (Masked + Protected).
```

Set these in GitLab CI/CD variables (UI):

- `CF_REPORT_API_TOKEN` (masked, protected)
- `CF_REPORT_CONFIG_YAML` (prefer non-secret content)
- `CF_REPORT_SMTP_PASSWORD` (masked, protected) if email is enabled

## Email in CI (SMTP password handling)

The simplest CI approach is to provide `CF_REPORT_SMTP_PASSWORD` as a CI secret and omit `smtp_password` from the config file.

Example:

```bash
cat > .ci/config.yaml <<'YAML'
api_token: ""
cache_dir: ".ci-cache/cf-report"
output_dir: ".ci-output"
zones:
  - id: "your-zone-id"
    name: "example.com"
email:
  enabled: true
  smtp_host: "smtp.example.com"
  smtp_user: "reports@example.com"
  recipients:
    - "security@example.com"
YAML
```

> Warning: this config has no password. The password comes from `CF_REPORT_SMTP_PASSWORD`. Do not print environment variables or enable shell tracing.

## Troubleshooting

| Error | Likely cause | Fix |
| --- | --- | --- |
| `Authentication failed` | Missing/wrong token | Verify `CF_REPORT_API_TOKEN` (or fallback `CLOUDFLARE_API_TOKEN`) and token permissions |
| `No zones in config` | Config missing `zones` or wrong `--config` path | Check file content and `--config` path |
| `Config already exists` | `cf-report init` used in CI | Do not run `init` in CI |
| `Cache lock timeout` | Concurrent jobs sharing the same cache | Use separate caches per branch/job, avoid parallel runs over one cache |
| `Fingerprint mismatch` | `--cache-only` used after changing parameters | Prefer `sync` + `report` without `--cache-only` |

### Cache grows forever

Schedule periodic cleanup (example):

```bash
cf-report clean --older-than 90
```

## See also

- [Configuration reference](USAGE.md)
- [Dashboard verification](verify-report-vs-cloudflare.md)

## Summary

- Use `CF_REPORT_API_TOKEN` as a CI secret.
- Store config as a file in the repo or as a CI variable that writes to a file.
- Persist both `cache_dir` and `output_dir/outputs` using CI caches.
- Upload PDFs as artifacts.
