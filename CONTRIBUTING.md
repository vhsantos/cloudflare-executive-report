# Contributing

User-facing install and CLI usage live in **[README.md](README.md)**. This file is for people changing the codebase.

## Dev setup

From the repository root:

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
pytest
```

## Architecture (mental model)

1. **`fetchers/registry.py`** - `FETCHER_REGISTRY`: stream id → fetcher instance. Defines iteration order for sync and report.
2. **`fetchers/types.py`** - `Fetcher` protocol: `stream_id`, `cache_filename`, `collect_label`, `outside_retention`, `fetch`, `append_live_today`.
3. **`sync/orchestrator.py`** - For each zone and each day in the chosen window, calls **`process_day`** for each selected stream. Builds the JSON report by reading cache + optional live-today payloads and **`SECTION_BUILDERS`**.
4. **`aggregate.py`** - Section builders (`build_*_section`) and **`SECTION_BUILDERS`** map (must use the **same keys** as `FETCHER_REGISTRY`).
5. **`retention.py`** - Shared date/window helpers if you want plan-aware cutoffs (optional; you can keep rules inside the fetcher).

The CLI and cache index are **generic**: you should not need to edit them for a normal new stream.

## Adding a new dataset (stream)

Use a stable **`stream_id`** string (lowercase, no spaces), e.g. `workers`.

### 1. Implement a fetcher

Create **`src/cloudflare_executive_report/fetchers/<name>.py`** with a class that satisfies **`Fetcher`**:

| Piece                                        | Purpose                                                                                             |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `stream_id`                                  | Key in report JSON and registry (e.g. `"workers"`).                                                 |
| `cache_filename`                             | File name under each day dir (e.g. `"workers.json"`).                                               |
| `collect_label`                              | Human label in cache warnings (e.g. `"Workers"`).                                                   |
| `outside_retention(day, plan_legacy_id=...)` | Return `True` to write `_source: "null"` without API call.                                          |
| `fetch(client, zone_id, day)`                | Return a **dict** (or JSON-serializable structure) stored as envelope **`data`**.                   |
| `append_live_today(...)`                     | Return `([], [], False)` if not supported; otherwise partial-day list + warnings + rate-limit flag. |

Use **`client.graphql(...)`** for Analytics API, or **`client.sdk`** for REST.

### 2. Register the fetcher

In **`fetchers/registry.py`**:

- Import your class.
- Add **`"your_id": YourFetcher()`** to **`FETCHER_REGISTRY`** (order defines default `--types` order).

### 3. Add a report section

In **`aggregate.py`**:

- Implement **`build_your_section(daily_api_data, *, top=10) -> dict`** where `daily_api_data` is a list of **`data`** blobs from cache (same shape your fetcher stores).
- Add **`"your_id": build_your_section`** to **`SECTION_BUILDERS`**.

Keys in **`FETCHER_REGISTRY`** and **`SECTION_BUILDERS`** must match for every stream that appears in the report.

### 4. Retention (optional)

- Either add helpers in **`retention.py`** and tests in **`tests/test_retention.py`**, or implement windows only inside **`outside_retention`** / **`append_live_today`**.

### 5. Tests

- Add **`tests/test_aggregate.py`** (or similar) cases for your section builder.
- Consider a test that **`set(FETCHER_REGISTRY.keys()) == set(SECTION_BUILDERS.keys())`** (already present in this repo).

### 6. Exports (optional)

If other code needs your helpers, export them from **`fetchers/__init__.py`**.

## What you usually do **not** touch

- **`cli.py`** / **`sync/options.py`** - types default from **`registered_stream_ids()`**.
- **`cache/index.py`** - generic `streams` dict.
- **`sync/day_processor.py`** - uses **`day_cache_path`** and the protocol only.

## PR hygiene

- Run **`ruff`** and **`pytest`**.
- Keep changes focused; match existing style and typing.
