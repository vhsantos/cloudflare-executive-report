# Adding a New Data Stream

This guide walks through every layer you need to touch to introduce a new
Cloudflare data stream into the pipeline, using a fictional `example` stream
as the running illustration.

Follow the steps in order - each layer depends on the previous one.

> [!TIP]
> Fully-annotated skeletons you can copy and adapt:
> - `src/cloudflare_executive_report/fetchers/example.py`
> - `src/cloudflare_executive_report/aggregators/example.py`
> - `src/cloudflare_executive_report/pdf/streams/example.py`
> - `tests/test_example_stream.py`
>
> Find-and-replace `example` / `Example`, fill in the GraphQL query and field
> mappings, then delete this sentence.

---

## Quick checklist

- [ ] 1. Create `fetchers/example.py` (fetcher class + standalone fetch functions)
- [ ] 2. Register in `fetchers/registry.py`
- [ ] 3. Create `aggregators/example.py` (section builder)
- [ ] 4. Register in `aggregators/registry.py`
- [ ] 5. Add executive phrases to `executive/phrase_catalog.py` (optional)
- [ ] 6. Add evaluation logic to `executive/rules.py` (optional)
- [ ] 7. Create `pdf/streams/example.py` (PDF page, optional)
- [ ] 8. Wire PDF page in `pdf/loader.py` and `pdf/orchestrate.py` (optional)
- [ ] 9. Add `tests/test_example_stream.py`

---

## Step 1 - Create the fetcher

**File:** `src/cloudflare_executive_report/fetchers/example.py`

The skeleton already exists at that path. Key rules:

| ClassVar | Value | Example |
|---|---|---|
| `stream_id` | lowercase, no spaces - must match registry key | `"example"` |
| `cache_filename` | stored under each day directory | `"example.json"` |
| `collect_label` | human label used in log/warning messages | `"Example"` |
| `required_permissions` | Cloudflare token scopes needed | `("Zone > Zone Read", "Zone > Analytics Read")` |

Two standalone functions keep the class thin and testable:

- `fetch_example_for_bounds(client, zone_id, since_iso_z, until_iso_z)` - raw
  GraphQL call; returns the normalized `dict`.
- `fetch_example_for_date(client, zone_id, day)` - wraps bounds helper, adds
  `"date"` key.

The class methods only delegate:

```python
def fetch(self, client, zone_id, day, *, zone_meta):
    return fetch_example_for_date(client, zone_id, day)

def append_live_today(self, client, zone_id, zone_name, *, plan_legacy_id, zone_meta):
    # Return ([], [], False) if the stream does not support partial-day data.
    return [], [], False
```

### GraphQL conventions

- Use named operations (`query ExampleDay($zoneTag: String!, ...)`).
- Always pass `zoneTag_in: [$zoneTag]` as the zone filter.
- Use `datetime_geq` / `datetime_lt` for time-based streams; `date_geq` /
  `date_leq` for date-only streams.
- Never fetch more rows than needed - set `limit` as a named module constant.
- Keep query strings as module-level constants (`Q_EXAMPLE_DAY = """..."""`).

### Retention

Override `outside_retention` if the Cloudflare plan caps history. Return
`True` to write `_source: "null"` without making an API call.

```python
from cloudflare_executive_report.common.retention import date_outside_http_retention

def outside_retention(self, day: date, *, plan_legacy_id: str | None) -> bool:
    return date_outside_http_retention(day)
```

---

## Step 2 - Register the fetcher

**File:** `src/cloudflare_executive_report/fetchers/registry.py`

```python
from cloudflare_executive_report.fetchers.example import ExampleFetcher

FETCHER_REGISTRY: dict[str, Fetcher] = {
    ...
    "example": ExampleFetcher(),   # <-- add here; order = default sync / PDF order
}
```

The registry validator (`_validate_registry`) runs at import time and will
raise `ValueError` if `stream_id` does not match the dict key.

---

## Step 3 - Create the aggregator

**File:** `src/cloudflare_executive_report/aggregators/example.py`

```python
"""Example stream aggregation builder."""

from __future__ import annotations

from typing import Any


def build_example_section(
    daily_api_data: list[dict[str, Any]],
    *,
    top: int = 10,
) -> dict[str, Any]:
    """Aggregate example daily payloads into one report section."""
    total = 0
    for day in daily_api_data:
        total += int(day.get("total_count") or 0)
    return {
        "total_count": total,
        # ... add all other fields consumed by the PDF page
    }
```

Rules:

- Input is a list of `data` blobs, exactly as stored by the fetcher.
- Never call the API here - aggregate only.
- Return a flat `dict`; nested lists are fine for table data.
- Add `_human` variants using `format_count_human` / `format_bytes_human` from
  `common.formatting`.

---

## Step 4 - Register the section builder

**File:** `src/cloudflare_executive_report/aggregators/registry.py`

```python
from cloudflare_executive_report.aggregators.example import build_example_section

SECTION_BUILDERS: dict[str, SectionBuilder] = {
    ...
    "example": build_example_section,   # <-- key must match FETCHER_REGISTRY
}
```

The test `test_fetcher_registry_matches_section_builders` (in
`tests/test_aggregate.py`) asserts `set(FETCHER_REGISTRY.keys()) ==
set(SECTION_BUILDERS.keys())` - it will fail if the keys are out of sync.

---

## Step 5 - Executive phrases (optional)

If the stream should generate takeaways or actions in the executive summary,
add entries to `executive/phrase_catalog.py`:

```python
RULE_CATALOG: dict[str, PhraseEntry] = {
    ...
    "example_issue_found": {
        "id": "EXP-001",
        "service": "Example",
        "nist": ["SI-4"],
        "risk": {
            "text": "Example issue detected: {detail}.",
            "weight": 7,        # 1-10; required for risk state only
        },
        "action": {
            "text": "Resolve the example issue to restore normal operation.",
        },
    },
    "example_ok": {
        "id": "EXP-002",
        "service": "Example",
        "nist": ["SI-4"],
        "win": {"text": "Example health restored."},
    },
}
```

IDs must be globally unique across the catalog. Use a new prefix for your
service (e.g. `EXP-` for Example).

---

## Step 6 - Executive rules (optional)

Add evaluation logic inside `executive/rules.py` in
`build_executive_rule_output`:

```python
ex = as_dict(current_zone.get("example"))

example_total = as_int(ex.get("total_count"))
if example_total > EXAMPLE_THRESHOLD:
    add_takeaway(
        SECT_SIGNALS,
        "warning",
        "example_issue_found",
        state="risk",
        detail=example_total,
    )
    add_action("info", "example_issue_found", state="action")
```

Add any numeric thresholds to `common/constants.py` as named constants.

---

## Step 7 - PDF page (optional)

Create `pdf/streams/example.py` following the same structure as
`pdf/streams/cache.py`:

```python
"""Example analytics section for PDF reports."""

from __future__ import annotations

from typing import Any

from cloudflare_executive_report.pdf.stream_fragments import (
    append_missing_dates_note,
    append_stream_header,
)
from cloudflare_executive_report.pdf.primitives import get_render_context, kpi_row
from cloudflare_executive_report.pdf.theme import Theme


def collect_example_appendix_notes(
    example: dict[str, Any], *, profile: str
) -> list[str]:
    """Return appendix notes derived from example metrics."""
    if profile not in {"executive", "detailed"}:
        return []
    return []


def append_example_stream(
    story: list[Any],
    *,
    zone_name: str,
    period_start: str,
    period_end: str,
    example: dict[str, Any],
    missing_dates: list[str],
    theme: Theme,
    top: int,
) -> None:
    """Append the example PDF section to story."""
    styles = get_render_context().styles

    append_stream_header(
        story,
        styles,
        theme,
        blocks=set(),         # pass layout.blocks when using a layout spec
        stream_title="Example",
        zone_name=zone_name,
        period_start=period_start,
        period_end=period_end,
    )
    append_missing_dates_note(story, styles, set(), missing_dates)
    # ... render KPIs, charts, tables
```

---

## Step 8 - Wire into PDF loader and orchestrator (optional)

### `pdf/loader.py`

Add a `LoadResult` dataclass and a `load_example_for_range` function:

```python
@dataclass
class ExampleLoadResult:
    rollup: dict[str, Any]
    missing_dates: list[str]
    warnings: list[str] = field(default_factory=list)
    api_day_count: int = 0


def load_example_for_range(
    cache_root: Path,
    zone_id: str,
    zone_name: str,
    start: str,
    end: str,
    *,
    top: int,
) -> ExampleLoadResult:
    scratch = _load_cached_stream_days(
        cache_root, zone_id, zone_name, start, end,
        stream_id="example",
        stream_label="Example",
        metric_key="total_count",
    )
    rollup, missing, warns, n_api = _finalize_stream_load(
        scratch, top=top, build_rollup=build_example_section
    )
    return ExampleLoadResult(
        rollup=rollup,
        missing_dates=missing,
        warnings=warns,
        api_day_count=n_api,
    )
```

### `pdf/orchestrate.py`

1. Import `load_example_for_range` and `append_example_stream`.
2. Add `loaded_example = None` next to the other `loaded_*` variables.
3. In the stream loop (`for stream in spec.streams`), add:

```python
elif sid == "example":
    loaded_example = load_example_for_range(
        cache_root, zone_id, zone_name, spec.start, spec.end, top=spec.top
    )
    zone_warnings.extend(loaded_example.warnings)
    appendix_metric_notes.extend(
        collect_example_appendix_notes(loaded_example.rollup, profile=cfg.pdf.profile)
    )
```

4. In the detail render loop, add:

```python
elif sid == "example":
    if loaded_example is None:
        continue
    if loaded_example.api_day_count == 0:
        _warn_skip_no_api_data("Example", zone_name, spec.start, spec.end)
        continue
    append_example_stream(
        story,
        zone_name=zone_name,
        period_start=spec.start,
        period_end=spec.end,
        example=loaded_example.rollup,
        missing_dates=loaded_example.missing_dates,
        theme=th,
        top=spec.top,
    )
```

---

## Step 9 - Tests

Create `tests/test_example_stream.py`:

```python
"""Tests for the example stream aggregator."""

from cloudflare_executive_report.aggregators.example import build_example_section


def test_build_example_section_empty() -> None:
    out = build_example_section([])
    assert out["total_count"] == 0


def test_build_example_section_sums_days() -> None:
    days = [
        {"total_count": 10},
        {"total_count": 25},
    ]
    out = build_example_section(days, top=5)
    assert out["total_count"] == 35
```

Also add a fetcher skeleton test following `tests/test_fetchers_security_unit.py`
as the model.

---

## What you never touch for a normal stream

| File | Why |
|---|---|
| `cli.py` | Types default from `registered_stream_ids()` |
| `sync/options.py` | Same - auto-picked from registry |
| `cache/index.py` | Generic `streams` dict |
| `sync/day_processor.py` | Uses `day_cache_path` and the protocol only |
| `fetchers/types.py` | The `Fetcher` protocol - extend only if adding a new method |

---

## Naming conventions

| Thing | Rule | Example |
|---|---|---|
| `stream_id` | Snake-case, no spaces | `"email_routing"` |
| `cache_filename` | `<stream_id>.json` | `"email_routing.json"` |
| `collect_label` | Title-case human name | `"Email Routing"` |
| Phrase IDs | `SERVICE-NNN` prefix | `"EML-001"` |
| Fetch function | `fetch_<stream>_for_bounds` / `fetch_<stream>_for_date` | `fetch_email_routing_for_date` |
| Section builder | `build_<stream>_section` | `build_email_routing_section` |
| Load result | `<Stream>LoadResult` | `EmailRoutingLoadResult` |
| PDF append fn | `append_<stream>_stream` | `append_email_routing_stream` |
