# TODO

## Documentation

- [ ] Add clear instructions how/which/why each token Permission policies are need.

## Token

- [ ] check if token exists
- [ ] validate if token has access to the corrects polices (maybe put the token requirements on each stream)

## Configuration

- [ ] Option to add all zones to the config.
- [ ] log_level:
  - [ ] should contain critical, warning, info, debug
  - [ ] command line should allow -v -vv -vvv
  - [ ] code actaully only shows warnings and info and a crazy debug mode (with a lot of http info)
  - [ ] we should have the none option (--quit mode ?? )
  - [ ] redirect output to a log file

## Performance and Cloudflare API limits

- [ ] Baseline API cost by command and stream.
  - Map expected GraphQL calls for `sync` and `report` (including `--refresh-health` paths).
  - Publish a simple per-stream query budget in docs, with assumptions (zones, days, streams).
- [ ] Batch compatible adaptive queries to reduce total GraphQL calls.
  - Identify fetchers that hit similar adaptive endpoints and can share one query payload.
  - Keep output shape unchanged so report logic and tests do not need behavioral changes.
- [ ] Add non-retryable GraphQL error classification and early exit rules.
  - Define which errors should fail fast (for example: bad query shape, invalid field, auth/permission).
  - Avoid extra retries for those classes and return explicit error messages.
- [ ] Make throttling and backoff configurable.
  - Expose retry/backoff knobs in config (with safe defaults) for high-volume multi-zone runs.
  - Document recommended values for conservative and aggressive profiles.
- [ ] Add CLI guardrails for high-cost `--types` selections on lower plans.
  - Warn or fail early when selected stream combinations and date windows are likely to exceed budget.
  - Include plan-aware guidance in the error/warning text.
- [ ] Add per-run API observability counters.
  - Track and log totals: GraphQL attempted, succeeded, failed, and rate-limited.
  - Print one summary line per run so CI logs show API health at a glance.

## Validated

- [ ] Executive summary wording can still be incoherent in some scenarios.
  - PDF labels were clarified (`Operational status` and `Security score`), but we still need rule-level checks so status/takeaways do not conflict.

## Security and posture checks (backlog)

Suggested order when choosing the next item: bot posture (if API stable for your tiers), then rate-limit presence (reuse ruleset enumeration), then WAF/CRS depth (after durable API fields), then multi-zone ranking as a product call, Zero Trust only as a deliberate scope expansion.

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

### Guidelines for implementing a new check

1. Verify against current Cloudflare API docs (method + response shape).
2. Add or extend `zone_health` or the relevant aggregator output; no fake defaults.
3. Add phrase (+ NIST ids) in `phrase_catalog`; wire rule in `rules.py`; add `pytest` for the rule and for unavailable/edge cases.
4. Keep executive copy short; put dashboard path in action text only when it stays accurate.
5. If plan-gated, emit unavailable or info, not a false critical.

### Historical Reproducibility (evaluate later)

Observed behavior to document and revisit:

- `--cache-only` reuses only `cf_report.json` (current snapshot), not history files.
- Snapshot reuse requires exact fingerprint match (`start`, `end`, `zones`, `top`, `types`, `include_today`).
- Changing `top` or `types` for an old period breaks reuse, even if cached daily data exists.
- Reducing configured zones (for example, from 5 zones to 1) also breaks cache-only reuse because
  `zones` is part of the strict fingerprint, even when the requested single-zone data already exists
  in the snapshot.
- When fingerprint mismatch happens (normal report run), PDF build may fetch fresh `zone_health` from "today",
  which can diverge from the original report period context.
- Comparison semantics can become confusing when zone set changes over time (for example, month N had 5 zones,
  month N+1 has 15 zones): strict fingerprint protects reproducibility, but blocks practical subset reruns.

Questions for future evaluation:

1. Should we support opt-in history snapshot lookup by exact fingerprint in cache-only mode?
2. Should we support reproducible reruns for old periods with modified layout/profile options but fixed historical health?
3. Should profile-only changes bypass fingerprint mismatch logic (if data inputs are unchanged)?
4. Should we add an explicit mode flag for "strict historical replay" versus "fresh health + cached streams"?
5. Should cache-only allow subset-zone replay when requested zones are a subset of snapshot zones and all
   other fingerprint fields match?
6. If subset-zone replay is allowed, should comparison and portfolio behavior be recomputed only for the
   selected zone set, with explicit labeling in the PDF/JSON metadata?

```bash
cf-report  report  -o output.pdf --start 2026-04-06 --end 2026-04-08
cf-report  report  -o output.pdf --start 2026-04-06 --end 2026-04-08 --cache-only
cf-report  report  -o output.pdf --start 2026-04-09 --end 2026-04-10
# Everything works... except, if we ran it again
cf-report  report  -o output.pdf --start 2026-04-06 --end 2026-04-08 --cache-only
Error: No matching report snapshot for this request. Run `cf-report report` without --cache-only first, then retry.

## 🏗️ Refactoring & Architecture (Technical Debt)

- [ ] **P-01: Async/Concurrency for Zone Processing (High Effort)**
  - **Context**: Current processing is sequential (zones → days → streams). A setup with 10 zones and 30 days results in ~1,200 sequential API calls, causing slow sync times.
  - **Goal**: Implement `asyncio` with `httpx.AsyncClient` to process zones and days in parallel.
  - **Constraints**: Must respect Cloudflare rate limits; implementation should include a semaphore or rate-limiter to prevent 429s.

- [ ] **A-01: Refactor `sync/orchestrator.py` (God Function)**
  - **Context**: The file is ~450 lines and mixes sync logic, JSON assembly, rotation, and cleanup. `_run_sync_locked` is overly nested and complex.
  - **Goal**: Split into `sync/orchestrator.py` (sync logic), `report/json_builder.py` (JSON assembly), and `sync/clean.py` (cleanup logic).

- [ ] **A-03: Resolve `report/` and `sync/` Package Overlap**
  - **Context**: Report JSON assembly is currently scattered between the orchestrator and `report/` modules, making data flow hard to trace.
  - **Goal**: Move all JSON report assembly logic into the `report/` package. The `sync/` package should strictly manage on-disk cache synchronization.

- [ ] **A-02: Transition Fetcher Registry to Factory/DI Pattern**
  - **Context**: Fetchers are module-level singletons created at import time, preventing easy dependency injection or per-run configuration.
  - **Goal**: Replace `FETCHER_REGISTRY` with a factory that supports lazy initialization and injection of mock clients for tests.

- [ ] **A-05: Consolidate `SyncMode` Logic**
  - **Context**: Mapping `SyncMode` (e.g., `this_week`) to date ranges is duplicated across orchestrator and resolver modules.
  - **Goal**: Centralize all date range resolution logic into `common/period_resolver.py`.

- [ ] **B-03: Audit Loop Closures (Fragility)**
  - **Context**: Reviewer noted that `read_stream` closures in `orchestrator.py` rely on default argument capture (`stream_id=sid`), which is correct but fragile to refactoring.
  - **Goal**: Audit closures and consider converting to `functools.partial` for better stability.

## 🧪 Testing Gaps (Hardening)

- [ ] **T-03: Reliability Tests for `cache/lock.py`**
  - **Context**: PID-based lock recovery was implemented to handle stale locks, but edge cases like high contention and timeout triggers are untested.
  - **Goal**: Add tests verifying lock acquisition, release, timeout triggers, and successful recovery from dead process IDs.

- [ ] **T-04: Integration Tests for SMTP Send Path**
  - **Context**: SMTP configuration is validated at runtime, but the actual `send_pdf_report_email` dispatch flow (attachments, placeholders) is untested.
  - **Goal**: Add an integration test using a mocked SMTP server (e.g., `aiosmtpd` or `pytest-localserver`) to verify the full email flow.

## 🎯 Coverage Goals (Future)

Current: ~75%
Target: 85%

Priority files to improve:
- [ ] `aggregate.py` (86% → 100%) - missing error paths and edge cases
- [ ] `report/command_flow.py` (59% → 85%) - mock more sync/health failure branches
- [ ] `sync/orchestrator.py` (75% → 90%) - test more sync modes and CLI edge cases
- [ ] `fetchers/*.py` - improve unit test coverage for individual stream fetchers
- [ ] `zone_health.py` (68% → 85%) - test more Cloudflare API error scenarios
