# TODO

## Executive summary narrative quality

- [ ] Replace hardcoded phrase "reliability stayed healthy" with rule-based wording driven by `status_5xx_rate_pct` (and optionally `status_4xx_rate_pct`).
- [ ] Define explicit thresholds for reliability labels (healthy / attention / critical) and keep them in shared constants.
- [ ] Ensure takeaway wording remains truthful for extreme values (e.g., very high 5xx).
- [ ] Add unit tests for narrative wording across threshold boundaries.

## Adaptive HTTP integration follow-up

- [ ] Confirm `http_adaptive` metrics are always included in report runs used for executive summaries (`--types` usage/documentation).
- [ ] Add a fallback explanatory note when latency percentiles are unavailable and only origin average latency is present.
- [ ] Decide whether `origin_response_duration_avg_ms` should be shown directly in executive PDF KPI rows.

## Product/content consistency

- [ ] Align executive takeaways with verdict logic to avoid contradictory messaging.
- [ ] Add a short "How to read reliability metrics" section in docs for non-technical stakeholders.

## Performance and Cloudflare API limits

- [ ] Audit total GraphQL calls per `sync`/`report` run and document query budget per stream.
- [ ] Reduce redundant queries by batching compatible adaptive metrics into fewer requests where possible.
- [ ] Add smarter short-circuit logic for known non-retryable GraphQL errors to avoid extra calls.
- [ ] Add configurable throttling/backoff strategy for high-volume multi-zone runs.
- [ ] Add guardrails for `--types` combinations that can exceed budget on Free plan.
- [ ] Add observability counters in logs (queries attempted, succeeded, failed, rate-limited) per run.
- [ ] Evaluate cache-first behavior for PDF/report generation to avoid unnecessary live API requests.
