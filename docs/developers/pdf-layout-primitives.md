# PDF Layout Primitives

Short guide for developers working on executive report PDFs. These helpers live in `src/cloudflare_executive_report/pdf/primitives.py` and assume an active **render context** (see below).

---

## Prerequisite: Render Context

Before building any flowables, the orchestrator calls:

- `initialize(theme)` - once per report
- `clear_render_context()` - in a `finally` block when done

The context supplies **theme**, **styles**, and **content width**. Helpers like `table_with_bars` and `flex_row` read it via `get_render_context()`.

> ⚠️ **Testing:** If you build primitives directly in tests, call `initialize(theme)` first and `clear_render_context()` after.

## Quick Reference

| You need...                         | Use                                                             |
| ----------------------------------- | --------------------------------------------------------------- |
| One ranked list, full width         | `table_with_bars(title, rows, ratios)`                          |
| One ranked list inside a map layout | `table_with_bars(..., total_width_in=X, show_outer_card=False)` |
| 2 or 3 ranked lists side by side    | `flex_row([(t1, r1, rt1), (t2, r2, rt2)])`                      |
| Same as above + standard spacer     | `flex_row_section(story, tables)`                               |
| KPI big numbers in a header band    | `kpi_row([(label, value), ...])`                                |

---

## Related chart helpers

### `table_with_bars` - Single Card

**What it does:** Creates one card with a title and a ranked table.

```md
┌──────────────────────────────────────────────┐
│  Cache Performance                           │
│  ┌─────────────────────────────────────────┐ │
│  │ Hit              │ 17.8K  │ ████████░░ ││ |
│  │ Revalidated      │ 16.7K  │ ███████░░░ ││ |
│  │ Miss             │ 7.7K   │ ███░░░░░░░ ││ |
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

**When to use:**

- A **single** ranked list at full width
- Inside a custom layout (e.g., next to a map) with `show_outer_card=False`

**Example:**

```python
# Full width (default)
story.append(table_with_bars("Cache performance", rows, (0.40, 0.18, 0.42)))

# Custom width, no outer border (for map side-by-side)
story.append(table_with_bars("Top countries", rows, (0.42, 0.18, 0.40),
    total_width_in=3.0, show_outer_card=False))
```

**Row format:** Each row is `[label, count_string, bar_width]` where `bar_width` is a float between 0 and 1. Use `ranked_rows_from_dicts()` to build from API data.

### `flex_row` - Multiple Cards Side by Side

**What it does:** Places 1 to 3 cards horizontally in a single row. Width is auto-calculated: `(content_width - gaps) / n`.

```md
┌──────────────┐  gap  ┌──────────────┐  gap  ┌──────────────┐
│ HTTP Methods │       │   Services   │       │   Actions    │
│ ┌──────────┐ │       │ ┌──────────┐ │       │ ┌──────────┐ │
│ │ GET 80%  │ │       │ │ WAF 45%  │ │       │ │ Block 30%│ │
│ │ POST 15% │ │       │ │ Rate 30% │ │       │ │ Chal 25% │ │
│ └──────────┘ │       │ └──────────┘ │       │ └──────────┘ │
└──────────────┘       └──────────────┘       └──────────────┘
<────────────────── content width with gaps ──────────────────>
```

**When to use:** You have 2 or 3 related ranked tables that belong side by side.

**Example:**

```python
# Two tables
story.append(flex_row([
    ("Top query names", qnames, (0.52, 0.18, 0.30)),
    ("Top record types", rtypes, (0.28, 0.18, 0.54)),
]))

# Three tables
story.append(flex_row([
    ("HTTP methods", method_rows, method_ratios),
    ("Security services", svc_rows, sec_ratios),
    ("Security actions", rows_top, sec_ratios),
]))
```

**Rules:** `len(tables)` must be 1, 2, or 3. Use 1 table only when you want auto-width (same as `table_with_bars`).

### `flex_row_section` - Append + Spacer

**What it does:** If `tables` is not empty, appends `flex_row(tables)` + a small `Spacer` to `story`.

**When to use:** Most common case - you want the row plus standard spacing.

**When NOT to use:** You need custom spacing or additional flowables between cards.

**Example:**

```python
# Instead of:
if tables:
    story.append(flex_row(tables))
    story.append(Spacer(1, PDF_SPACE_SMALL_PT))

# Just write:
flex_row_section(story, tables)
```

### `kpi_row` - KPI Band

**What it does:** Creates a full-width band of key-value pairs with large numbers and optional indicators.

```md
┌─────────────┐  │  ┌─────────────┐  │  ┌─────────────┐
│ Total Reqs  │  │  │  Bandwidth  │  │  │  Cache Hit  │
│   94.5K     │  │  │    5.6 GB   │  │  │   19.0% ▼   │
└─────────────┘  │  └─────────────┘  │  └─────────────┘
```

**When to use:** Top-of-stream summary numbers (requests, bandwidth, error rates). Not for ranked breakdowns.

**Example:**

```python
story.append(kpi_row([
    ("Total requests", "94.5K"),
    ("Bandwidth", "5.6 GB"),
    ("Cache hit ratio", "19.0%", "R:▼5%"),  # optional indicator
]))
```

**Indicator prefixes:**

| Prefix | Color   | Example    |
| ------ | ------- | ---------- |
| `G:`   | Green   | `"G:▲12%"` |
| `R:`   | Red     | `"R:▼5%"`  |
| `N:`   | Neutral | `"N:0%"`   |

---

## Charts (Related, Not in `primitives.py`)

Time series charts live in `pdf/stream_fragments.py`:

```python
if "timeseries" in blocks:
    chart_bytes, subtitle = prepare_dual_line_daily_series(...)
    append_timeseries_chart(story, styles, theme, blocks, chart_bytes, subtitle)
```

> ⚠️ **Important:** Keep `if "timeseries" in blocks` outside the helper. The `prepare_*` functions do expensive aggregation and rendering. Don't call them if the block is disabled.

### Time-series color policy

Line charts follow a fixed semantic color policy from `pdf/charts.py`:

| Chart shape | Color order                     | Intended meaning                                             |
| ----------- | ------------------------------- | ------------------------------------------------------------ |
| Single line | `accent`                        | Primary Cloudflare-associated metric                         |
| Dual line   | `accent`, `primary`             | Cloudflare-associated metric first, counterpart second       |
| Triple line | `accent`, `primary`, `tertiary` | Primary series, secondary series, then other/tertiary series |

For stream usage, keep legends aligned with data tuple order so colors remain semantically stable.

---

## File Map

| What                                                         | Where                     |
| ------------------------------------------------------------ | ------------------------- |
| `table_with_bars`, `flex_row`, `flex_row_section`, `kpi_row` | `pdf/primitives.py`       |
| `initialize`, `get_render_context`, `clear_render_context`   | `pdf/primitives.py`       |
| `append_timeseries_chart`, `append_chart_section`            | `pdf/stream_fragments.py` |
| Stream assembly                                              | `pdf/streams/*.py`        |
