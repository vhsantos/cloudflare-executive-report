# How to read reliability metrics (executive summary)

This note is for stakeholders who see **4xx rate**, **5xx rate**, **Edge p50/p95**, and **Origin response** on the executive summary. Numbers come from Cloudflare **HTTP adaptive** analytics (sampled traffic), not from every single request.

## What each field means

- **4xx rate** - Share of sampled requests where the edge returned a **client error** (for example not found, auth required, or bad request). A higher value often points to broken links, API misuse, or aggressive bots probing URLs.
- **5xx rate** - Share of sampled requests where the edge returned a **server error**. This is the main signal for **reliability problems** at the origin or upstream (timeouts, application crashes, overload).
- **Edge p50 / p95 latency** - **Percentiles** of how long responses took at the edge for sampled traffic. Half of responses were at or below p50; 95% were at or below p95. Large gaps between p50 and p95 mean some users see much slower responses than others.
- **Origin response** - **Average** time the origin took to respond for sampled traffic (not a percentile). It helps explain delays when the problem is behind Cloudflare rather than on the edge.

## Narrative and bands

The one-line **reliability** text on the report uses **5xx** first: low 5xx is described as healthy; elevated 5xx as needing attention; very high 5xx as poor. If **4xx** is high even when 5xx looks fine, the text calls that out separately. Exact cutoffs are defined in `executive/constants.py` (`RELIABILITY_5XX_*`, `RELIABILITY_4XX_HIGH_PCT`).

## When numbers or percentiles are missing

If adaptive HTTP was not synced for the period, or there were **no analyzed requests**, error rates may show as zero and the narrative explains that the data is unknown. If **p50/p95** are missing but **origin average** is present, a short footnote states that only the average origin time is available.

## Caveats

Adaptive metrics are **approximate** and depend on Cloudflare sampling and your plan. They are best read as **trends and orders of magnitude**, not as exact accounting.
