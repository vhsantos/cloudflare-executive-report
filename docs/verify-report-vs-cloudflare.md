# Check your report against Cloudflare

This guide helps you **confirm that what the report says matches what you see in the Cloudflare dashboard** for the same website (zone) and the same time range.

**On the PDF, each finding looks like:** `[!] [TLS-002] ...`
The short code in brackets (e.g., **TLS-002**) is the **check ID**. Use it to find the right section below.

---

## Quick start

1. Open your **PDF** and note the **zone name**, **dates (UTC)**, **Verdict**, **Score**, **KPIs**, **Takeaways**, and **Actions**.
2. Log in to **Cloudflare**, select the **same zone**, and open the areas this guide points to.
3. Compare settings using the **same date range** (UTC).
4. If something looks wrong after you fix the dashboard, the report may be using **cached data** - see *When report and dashboard disagree*.

---

## Verdict (Healthy / Warning / Critical)

| What you see | Meaning                                                                       |
| ------------ | ----------------------------------------------------------------------------- |
| **Healthy**  | Zone is active and has no critical issues.                                    |
| **Warning**  | Something needs attention (e.g., many warnings, proxied DNS with no traffic). |
| **Critical** | Zone is not active or has a serious problem.                                  |

**To verify:** Go to Cloudflare **Overview** → check zone status is **Active**.

---

## Security score

The **Score** (e.g., `72 (C)`) is **calculated from the risks shown on the page**. It is not a single number copied from Cloudflare.

**To verify:** Look at the **number and severity of risk takeaways**. Fixing real issues should increase the score.

---

## Match KPIs to the dashboard

### Zone and encryption

| On the report | Where to check in Cloudflare             |
| ------------- | ---------------------------------------- |
| Zone status   | **Overview** → zone should be **Active** |
| TLS/SSL Mode  | **SSL/TLS** → **Overview**               |
| Always HTTPS  | **SSL/TLS** → **Edge Certificates**      |

**Check IDs:** `TLS-001` through `TLS-014`, `CMP-027`, `COR-004`, `ACT-001` through `ACT-004`

---

### Traffic and security

| On the report                                 | Where to check                            |
| --------------------------------------------- | ----------------------------------------- |
| Requests, encrypted requests, cache hit ratio | **Analytics** → HTTP (use same UTC dates) |
| Blocked/challenged, mitigation rate           | **Security** → **Events**                 |

**Small differences are normal** (sampling, time boundaries). Large mismatches = wrong date range or zone.

**Check IDs:** `CMP-010`, `CMP-011`, `CMP-020` through `CMP-025`

---

### Performance

| On the report           | Where to check       |
| ----------------------- | -------------------- |
| 4xx/5xx errors, latency | **Analytics** → HTTP |

**Check IDs:** `COR-001`, `CMP-024`, `CMP-011`

---

### DNS

| On the report               | Where to check                                                  |
| --------------------------- | --------------------------------------------------------------- |
| DNS volume                  | **DNS** → **Analytics**                                         |
| Proxied vs DNS-only records | **DNS** → **Records** (orange cloud = proxied, grey = DNS-only) |

**Check IDs:** `APEX-001`, `APEX-002`, `DNS-001`, `DNS-010`, `COR-003`, `CMP-026`, `ACT-005`, `DNS-002`

---

### Certificates, audit, apex protection

| On the report      | Where to check                                 |
| ------------------ | ---------------------------------------------- |
| Certificate expiry | **SSL/TLS** → **Edge Certificates**            |
| Audit activity     | **Audit Logs** (if available for your account) |
| Apex protection    | **DNS** → root domain record (proxy on/off)    |

**Check IDs:** `CERT-001` through `CERT-003`, `COR-006`, `ACT-006`, `ACT-007`

---

## Posture checklist (fix by check ID)

When you see a check ID, verify and fix in the dashboard.

### WAF and security

| ID        | What to check                | Where to fix           |
| --------- | ---------------------------- | ---------------------- |
| `WAF-001` | WAF / managed rules          | **Security** → **WAF** |
| `WAF-002` | WAF and rate limiting review | **Security** → **WAF** |

### DDoS and Security Level

| ID                   | What to check              | Where to fix                                      |
| -------------------- | -------------------------- | ------------------------------------------------- |
| `SEC-001`            | Advanced DDoS protection   | **Network** → DDoS settings                       |
| `SEC-010`, `ACT-008` | Security Level off/minimal | **Security** → **Settings** → **Security Level**  |
| `SEC-011`            | Under Attack mode          | **Security** → **Settings** (confirm intentional) |
| `SEC-012`, `SEC-013` | Security Level info        | Same as above                                     |

### Browser integrity, email, opportunistic encryption

| ID        | What to check            | Where to fix                        |
| --------- | ------------------------ | ----------------------------------- |
| `SEC-014` | Browser Integrity Check  | **Security** → **Settings**         |
| `SEC-015` | Email obfuscation        | **Scrape Shield** or **Security**   |
| `TLS-014` | Opportunistic Encryption | **SSL/TLS** → **Edge Certificates** |

### Minimum TLS and TLS 1.3

| ID                              | What to check                | Where to fix                        |
| ------------------------------- | ---------------------------- | ----------------------------------- |
| `TLS-011`, `TLS-012`, `TLS-013` | Minimum TLS version, TLS 1.3 | **SSL/TLS** → **Edge Certificates** |

### Comparison lines (not a single toggle)

These compare two time periods or indicate missing data. Not fixed by one dashboard switch.

| ID                     | Meaning                                         |
| ---------------------- | ----------------------------------------------- |
| `CMP-001` to `CMP-004` | First report, wrong period, or missing data     |
| `CMP-010`, `CMP-011`   | Traffic or latency improved                     |
| `CMP-020`, `CMP-021`   | Threat activity vs traffic (period over period) |
| `CMP-022` to `CMP-025` | Other metric changes vs prior period            |
| `CMP-026`, `CMP-027`   | Regression (apex or SSL)                        |

---

## Actions block

These are **suggestions**. Your dashboard may already be updated.

| ID        | Meaning                      |
| --------- | ---------------------------- |
| `ACT-001` | Enable Always Use HTTPS      |
| `ACT-002` | Review HTTPS/encryption gaps |
| `ACT-003` | Review SSL/TLS mode          |
| `ACT-004` | Upgrade to Full (Strict)     |
| `ACT-005` | Proxy apex/root record       |
| `ACT-006` | Plan certificate renewal     |
| `ACT-007` | Review audit activity        |
| `ACT-008` | Use automatic Security Level |
| `DNS-002` | Review DNSSEC setup          |

---

## NIST appendix

If your PDF includes a **NIST Control Reference** section, it maps check IDs to compliance controls. Use it for audit purposes.

---

## When report and dashboard disagree

1. **Same zone and dates** → Compare UTC range on PDF to Analytics filter.
2. **Stale data** → Reports use cached data. Run a fresh sync after dashboard changes.
3. **Permissions** → If the tool couldn't read zone health or DNS, some KPIs show as unavailable.
4. **Missing DNS data** → Proxied counts and apex messages may be wrong until DNS syncs.

---

## For developers

- **IDs and wording:** `executive/phrase_catalog.py` (`RULE_CATALOG`)
- **When rules run:** `executive/rules.py` (`build_executive_rule_output`)
- **Verdict and score:** `executive/summary.py` (`_verdict`, `build_security_posture_score`)
- **PDF layout:** `pdf/streams/executive_summary.py`

Cloudflare may rename menu items over time. Update this document when the dashboard changes. This file is for **manual verification**, not automated tests.
