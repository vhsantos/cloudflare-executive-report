# Contributing to Cloudflare Executive Report

Thank you for your interest in improving the Cloudflare Executive Report tool!

## Adding a New Data Stream

To add a new data stream (e.g., "WAF Events" or "Workers Metrics"), follow these steps:

### 1. Create a Fetcher
Add a new file in `src/cloudflare_executive_report/fetchers/`.
- Inherit from a base fetcher pattern or implement the `fetch` and `append_live_today` methods.
- Define a `ClassVar` for `stream_id` and `cache_filename`.
- Register your fetcher in `src/cloudflare_executive_report/fetchers/registry.py`.

For a concrete example, see `src/cloudflare_executive_report/fetchers/http.py` or `src/cloudflare_executive_report/fetchers/security.py`.

### 2. Create an Aggregator
Add a new file in `src/cloudflare_executive_report/aggregators/`.
- Implement a `build_<stream>_section` function that takes a list of daily payloads and returns a consolidated dictionary.
- Register the builder in `src/cloudflare_executive_report/aggregators/registry.py`.

For a concrete example, see `src/cloudflare_executive_report/aggregators/http.py`.

### 3. Add Executive Rules (Optional)
If the new stream should impact the executive summary:
- Add new phrases to `src/cloudflare_executive_report/executive/phrase_catalog.py`.
- Add evaluation logic to `src/cloudflare_executive_report/executive/rules.py`.

## Coding Standards

- **Type Hints**: All functions must have type hints.
- **Docstrings**: Public functions must have docstrings describing *what* the function does.
- **No Magic Numbers**: Move thresholds and constants to `src/cloudflare_executive_report/common/constants.py`.
- **Tests**: Add unit tests in `tests/` for any new logic.

## Development Workflow

1. Install dependencies: `pip install -e ".[dev]"`
2. Run tests: `pytest`
3. Lint with Ruff: `ruff check .`
