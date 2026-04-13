# TODO

## Executive summary narrative quality

- [ ] Replace hardcoded phrase "reliability stayed healthy" with rule-based wording driven by `status_5xx_rate_pct` (and optionally `status_4xx_rate_pct`).
- [ ] Define explicit thresholds for reliability labels (healthy / attention / critical) and keep them in shared constants.
- [ ] Ensure takeaway wording remains truthful for extreme values (e.g., very high 5xx).
- [ ] Add unit tests for narrative wording across threshold boundaries.

## Adaptive HTTP integration follow-up

- [ ] Confirm `http_adaptive` metrics are always included in report runs used for executive summaries (`--types` usage/documentation).
- [ ] Decide whether `origin_response_duration_avg_ms` should be shown directly in executive PDF KPI rows.

## Product/content consistency

- [ ] Align executive takeaways with verdict logic to avoid contradictory messaging.
- [ ] Add a short "How to read reliability metrics" section in docs for non-technical stakeholders.
- [ ] Refactor PDF executive summary to reuse `executive_summary` from already-built report JSON (single source of truth), instead of recomputing summary in PDF path.
  - Context: `cf-report report` currently runs sync/write JSON, then PDF recomputes executive summary from cache + extra context.
  - Issue: this duplicated logic can drift between JSON and PDF (observed bug: PDF showing "First report..." while current JSON did not).
  - Goal: eliminate duplicated summary derivation and ensure PDF takeaways always match JSON takeaways exactly.
  - Acceptance criteria:
    - `cf-report report` PDF takeaways/actions match `cf_report.json` `executive_summary.takeaways` and `actions` for each zone.
    - No separate comparison gate decision in PDF-only path.
    - Add regression test covering a two-run period comparison where JSON and PDF outputs stay consistent.

## Performance and Cloudflare API limits

- [ ] Audit total GraphQL calls per `sync`/`report` run and document query budget per stream.
- [ ] Reduce redundant queries by batching compatible adaptive metrics into fewer requests where possible.
- [ ] Add smarter short-circuit logic for known non-retryable GraphQL errors to avoid extra calls.
- [ ] Add configurable throttling/backoff strategy for high-volume multi-zone runs.
- [ ] Add guardrails for `--types` combinations that can exceed budget on Free plan.
- [ ] Add observability counters in logs (queries attempted, succeeded, failed, rate-limited) per run.
- [ ] Evaluate cache-first behavior for PDF/report generation to avoid unnecessary live API requests.

## Validated

- [ ] Executive Summary incoherent.
  - Security level at Medium - consider High for sensitive data, but KPI SSL mode full/strict.

## Security and posture checks (backlog)

Suggested order when choosing the next item: HSTS (if one clear settings read), then bot posture (if API stable for your tiers), then rate-limit presence (reuse ruleset enumeration), then WAF/CRS depth (after durable API fields), then multi-zone ranking as a product call, Zero Trust only as a deliberate scope expansion.

- [ ] **Bot posture** - Surface bot protection level: off vs Bot Fight Mode vs Bot Management (plan-dependent).
  - Data: settings or account features API; product names change over time; small enum in `zone_health` or security rollup.
  - Shape: info or warning when bots are fully off on a proxied web zone; suppress DNS-only zones.
  - Risk: false positives on API-only zones; plan-gated features need clear unavailable handling.

- [ ] **WAF depth (managed ruleset / OWASP CRS)** - Separate "WAF on" from managed ruleset / CRS when the API exposes it.
  - Data: rulesets API; confirm stable phase/group IDs in docs.
  - Shape: optional second line (e.g. CRS off or simulate-only) if detectable.
  - Risk: UI/API naming churn; tests must tolerate unavailable.

- [ ] **Rate limiting** - Flag zones with zero rate limit rules when HTTP traffic is above an optional threshold.
  - Data: ruleset phase `http_ratelimit`; distinguish rate limits from WAF custom rules.
  - Shape: new rule + phrase; default to info to avoid noise on small sites.
  - Risk: many zones rely only on managed challenge; product judgment.

- [ ] **Rules clarity for executives** - CTO-readable counts: "N custom WAF rules, M rate limits" (ruleset-based, not legacy Firewall Rules API); optional dashboard hint in action text.
  - Data: largely present; extend phrase labeling if counts suffice without new API.

- [ ] **Declarative operator baseline (YAML)** - Optional external YAML (check id, severity, phrase key, optional when-expression) for Git-managed baselines.
  - Shape: loader merges or overrides subsets; keep `phrase_catalog` as source for text/NIST unless fully migrating.
  - Risk: two sources of truth; prefer generate-from-catalog or single compile step.

- [ ] **Multi-zone portfolio view** - After per-zone summaries, rank zones by critical risk count or by numeric score.
  - Shape: CLI output or multi-zone PDF cover table; no change to single-zone contract.
  - Risk: keep factual (counts), not subjective labels.

### Guidelines for implementing a new check

1. Verify against current Cloudflare API docs (method + response shape).
2. Add or extend `zone_health` or the relevant aggregator output; no fake defaults.
3. Add phrase (+ NIST ids) in `phrase_catalog`; wire rule in `rules.py`; add `pytest` for the rule and for unavailable/edge cases.
4. Keep executive copy short; put dashboard path in action text only when it stays accurate.
5. If plan-gated, emit unavailable or info, not a false critical.
