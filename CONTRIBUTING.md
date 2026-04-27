# Contributing

User-facing install and CLI usage live in **[README.md](README.md)**.
This file is for people changing the codebase.

---

## Dev setup

```bash
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
mypy src
pytest
```

---

## Architecture mental model

| Layer | Key file | Role |
|---|---|---|
| Fetcher | `fetchers/registry.py` | `FETCHER_REGISTRY` maps `stream_id` to fetcher instance |
| Protocol | `fetchers/types.py` | `Fetcher` protocol: `stream_id`, `cache_filename`, `collect_label`, `fetch`, `append_live_today` |
| Sync | `sync/orchestrator.py` | Calls `fetch` for each zone x day x stream; saves JSON envelopes |
| Aggregator | `aggregators/registry.py` | `SECTION_BUILDERS` maps `stream_id` to `build_*_section` function |
| PDF loader | `pdf/loader.py` | Reads day files, calls aggregator, returns typed `*LoadResult` |
| PDF page | `pdf/streams/*.py` | `append_<stream>_stream` + `collect_<stream>_appendix_notes` |
| Executive | `executive/rules.py` | Evaluates aggregated metrics; emits takeaways + actions |
| Phrases | `executive/phrase_catalog.py` | `RULE_CATALOG`: all approved text + NIST mappings |

Keys in `FETCHER_REGISTRY` and `SECTION_BUILDERS` must match exactly.
The test `test_fetcher_registry_matches_section_builders` enforces this.

---

## Adding a new data stream

The step-by-step guide (with code snippets for every layer) lives at:

**[docs/developers/add-new-stream.md](docs/developers/add-new-stream.md)**

A fully annotated skeleton that you can copy and adapt is at:

**`src/cloudflare_executive_report/fetchers/example.py`**
**`src/cloudflare_executive_report/aggregators/example.py`**
**`src/cloudflare_executive_report/pdf/streams/example.py`**
**`tests/test_example_stream.py`**

Quick checklist:

- [ ] `fetchers/<name>.py` - fetcher class + standalone `fetch_*_for_bounds` / `fetch_*_for_date`
- [ ] `fetchers/registry.py` - add `"<name>": YourFetcher()` to `FETCHER_REGISTRY`
- [ ] `aggregators/<name>.py` - `build_<name>_section(daily_api_data, *, top)`
- [ ] `aggregators/registry.py` - add `"<name>": build_<name>_section` to `SECTION_BUILDERS`
- [ ] `executive/phrase_catalog.py` - add phrases (optional)
- [ ] `executive/rules.py` - add evaluation logic (optional)
- [ ] `pdf/streams/<name>.py` - `append_<name>_stream` + `collect_<name>_appendix_notes` (optional)
- [ ] `pdf/loader.py` - `<Name>LoadResult` + `load_<name>_for_range` (optional)
- [ ] `pdf/orchestrate.py` - wire loader + stream renderer (optional)
- [ ] `tests/test_<name>_stream.py` - aggregator + fetcher unit tests

---

## Coding standards

- **Type hints**: every function parameter and return value.
- **Docstrings**: every public function - describe *what*, not *how*.
- **No magic numbers**: thresholds and limits go in `common/constants.py`.
- **No mock data**: every function must work against the real API.
- **Fail explicitly**: `raise` with a clear message; never `except: pass`.
- **ASCII only**: no em-dashes (`-` not `-`), no smart quotes (`"` not `"`).
- **Ruff**: `ruff check` and `ruff format` must pass before merging.
- **mypy**: `mypy src` must pass with no errors.

### Shared file locations

| Purpose | File |
|---|---|
| Date utilities | `common/dates.py` |
| Formatting helpers | `common/formatting.py` |
| Named constants | `common/constants.py` |
| API client helpers | `common/api.py` |

---

## Logging levels

| Level | Use |
|---|---|
| `DEBUG` | Cache hits/misses, file paths |
| `INFO` | Sync milestones, file writes |
| `WARNING` | Rate limits, missing data, skipped sections |
| `ERROR` | Unrecoverable failures |

---

## What you normally do **not** touch

| File | Reason |
|---|---|
| `cli.py` | Stream types default from `registered_stream_ids()` |
| `sync/options.py` | Same - auto-picked from registry |
| `cache/index.py` | Generic `streams` dict |
| `sync/day_processor.py` | Uses `day_cache_path` and the protocol only |
| `fetchers/types.py` | The `Fetcher` protocol - extend only if adding a new method |

---

## PR hygiene

- Run `ruff check src tests`, `ruff format src tests`, `mypy src`, `pytest`.
- Keep changes focused; match existing style and typing.
- One logical change per PR.
- Include or update tests for any new logic.

---

## Documentation files

| File | Audience |
|---|---|
| `README.md` | End users - install, configure, run |
| `CONTRIBUTING.md` (this file) | Contributors - dev setup, patterns |
| `docs/ARCHITECTURE.md` | Architecture overview and data flow |
| `docs/developers/add-new-stream.md` | Step-by-step guide for new streams |
| `docs/USAGE.md` | CLI reference |
| `docs/ci-cd.md` | CI/CD pipeline notes |
