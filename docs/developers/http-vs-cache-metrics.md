# HTTP vs Cache Metrics: Understanding the Differences

**Audience:** Developers maintaining this codebase
**Last Updated:** 2026-04-10
**Related Files:** `aggregators/http.py`, `aggregators/cache.py`, `common/aggregation_helpers.py`

---

## The Problem

Users see two sets of metrics that sound similar but show different numbers:

| Question          | HTTP Page | Cache Page                            |
| ----------------- | --------- | ------------------------------------- |
| "Cached requests" | 17.9K     | 61.5K (called "Served by Cloudflare") |
| "Uncached/Origin" | 76.6K     | 32.3K                                 |

**This is NOT a bug.** This document explains why.

---

## The Simple Truth

Both pages pull from the **same raw requests** but use **different GraphQL endpoints and different grouping logic**.

|                      | HTTP Page                     | Cache Page                                      |
| -------------------- | ----------------------------- | ----------------------------------------------- |
| **GraphQL endpoint** | `httpRequests1dGroups`        | `httpRequestsAdaptiveGroups`                    |
| **Filter**           | None (all traffic)            | `requestSource: "eyeball"` (human traffic only) |
| **Cache logic**      | Direct `cachedRequests` field | Reconstructed from `cacheStatus` buckets        |
| **Origin logic**     | `total - cachedRequests`      | Only `dynamic`, `miss`, `bypass` statuses       |

---

## Cache Status Mapping

### In Code (`aggregation_helpers.py`)

```python
CACHE_ORIGIN_FETCH_STATUSES = frozenset({"dynamic", "miss", "bypass"})
```

| Status        | Goes to "Served by Cloudflare"? | Goes to "Served by origin"? |
| ------------- | ------------------------------- | --------------------------- |
| `hit`         | ✅ Yes                          | ❌ No                       |
| `revalidated` | ✅ Yes                          | ❌ No                       |
| `expired`     | ✅ Yes                          | ❌ No                       |
| `stale`       | ✅ Yes                          | ❌ No                       |
| `none`        | ✅ Yes                          | ❌ No                       |
| `dynamic`     | ❌ No                           | ✅ Yes                      |
| `miss`        | ❌ No                           | ✅ Yes                      |
| `bypass`      | ❌ No                           | ✅ Yes                      |

**Key insight:** `revalidated` and `none` are the biggest sources of confusion.

- `revalidated` = cache hit that asked origin "still fresh?" (origin said yes, sent no data)
- `none` = no cache information (often API calls, WebSocket, non-cacheable responses)

---

## Why Numbers Differ

### HTTP Page

```python
cached_requests = sum(cachedRequests) from httpRequests1dGroups
uncached_requests = total_requests - cached_requests
```

**HTTP does NOT distinguish** between `revalidated`, `expired`, `none`, `dynamic`, `miss`, `bypass`. They all become "uncached."

### Cache Page

```python
served_by_cloudflare = total - sum(count where status in {dynamic, miss, bypass})
served_by_origin = sum(count where status in {dynamic, miss, bypass})
```

**Cache page includes** `revalidated`, `expired`, `stale`, and `none` in "Served by Cloudflare."

---

## The Gap Formula

```python
HTTP_uncached - Cache_origin = revalidated + expired + stale + none
```

Using real numbers:

```python
76.6K - 32.3K = 44.3K = 16.7K + 0.7K + 0K + 26.2K
```

**This is expected behavior, not an error.**

---

## What To Tell Stakeholders

When users ask about the difference:

> *"HTTP page shows strict cache hits only (HIT status). Cache page shows everything Cloudflare handled without origin sending full data (HIT + REVALIDATED + EXPIRED + STALE + NONE). Both are correct. Your origin only served DYNAMIC + MISS + BYPASS requests."*

---

## Recommended Labeling

If renaming KPIs for clarity:

| Page  | Old Label            | New Label          |
| ----- | -------------------- | ------------------ |
| HTTP  | Cached requests      | **Strict hits**    |
| HTTP  | Uncached requests    | **Non-hits**       |
| Cache | Served by Cloudflare | **Edge handled**   |
| Cache | Served by origin     | **Origin fetched** |

Add footnote:

> *"Strict hits = HIT status only. Edge handled = HIT + REVALIDATED + EXPIRED + STALE + NONE. Origin fetched = DYNAMIC + MISS + BYPASS."*

---

## Quick Reference Card

| User Question                 | Answer                                                 |
| ----------------------------- | ------------------------------------------------------ |
| Why don't numbers match?      | Different GraphQL endpoints + different grouping logic |
| Is there a bug?               | No                                                     |
| Which number is "correct"?    | Both, for their definitions                            |
| Which shows real origin load? | Cache page (origin fetched)                            |
| What is `revalidated`?        | Cache hit that validated with origin (no data sent)    |
| What is `none`?               | No cache info (API, WebSocket, etc.)                   |

---

## Related Code Files

- `fetchers/http.py` - HTTP page GraphQL query
- `fetchers/cache.py` - Cache page GraphQL query (includes `eyeball` filter)
- `aggregators/http.py` - HTTP page aggregation logic
- `aggregators/cache.py` - Cache page aggregation logic
- `common/aggregation_helpers.py` - `CACHE_ORIGIN_FETCH_STATUSES` constant
