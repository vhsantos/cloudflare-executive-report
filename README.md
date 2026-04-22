# ☁️ Cloudflare Executive Report

> Turn Cloudflare analytics into executive-ready PDF reports with security scores, NIST mappings, and multi-zone portfolio views.

[![Security: Read-Only](https://img.shields.io/badge/security-read--only-brightgreen.svg)](SECURITY.md)
[![PyPI version](https://img.shields.io/pypi/v/cloudflare-executive-report)](https://pypi.org/project/cloudflare-executive-report/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Coverage](https://img.shields.io/badge/coverage-75%25-yellowgreen)

---

## 🎯 Why this tool exists

Cloudflare dashboard data is great for daily ops, but **executives need more**:

| Problem                             | Solution                                    |
| ----------------------------------- | ------------------------------------------- |
| 📅 Dashboard only shows recent data | Historical windows beyond convenience       |
| 🌍 One zone at a time               | One report across many zones                |
| 📄 Raw numbers, no narrative        | Reusable PDFs with risk scoring and actions |
| 🔍 Too much detail                  | Concise leadership summaries                |

**Cloudflare Executive Report** fills that gap with local caching and deterministic PDF generation.

---

## ✨ What you get

| Feature                 | What it does for you                                   |
| ----------------------- | ------------------------------------------------------ |
| 💾 Historical cache     | Sync once, generate reports later - no re-querying     |
| 🌍 Multi-zone portfolio | One page with score, grade, and risks across all zones |
| 📋 Executive summary    | Verdict, KPIs, takeaways, and actions per zone         |
| 🎯 Security score       | 0-100 + grade, based on real risk takeaways            |
| 🔐 NIST mapping         | Compliance context for auditors                        |
| 📧 Email delivery       | Auto-send PDFs via SMTP after generation               |
| 🎨 Brand colors         | Match your company's primary/accent colors             |

---

## 📊 See it in action

Try the sample reports (generated from synthetic data):

|                          Minimal                           |                          Executive                           |                          Detailed                           |                            High Quality\*                             |
| :--------------------------------------------------------: | :----------------------------------------------------------: | :---------------------------------------------------------: | :-------------------------------------------------------------------: |
| 📄 [View PDF](docs/examples/report-minimal-png-medium.pdf) | 📊 [View PDF](docs/examples/report-executive-png-medium.pdf) | 🔬 [View PDF](docs/examples/report-detailed-png-medium.pdf) | ✨ [View PDF](docs/examples/report-detailed-svg-high-single-page.pdf) |

> \*SVG/high quality = larger file size, sharper visuals for printing

---

## 🚀 Quick start (30 seconds)

```bash
pip install cloudflare-executive-report
cf-report init
cf-report sync --last 30
cf-report report -o security-report.pdf
```

That's it. You just generated your first executive report.

---

## 🎚️ Report profiles (choose your depth)

|    Profile    | Cover | Portfolio | Zone summary | Details | Best for             |
| :-----------: | :---: | :-------: | :----------: | :-----: | -------------------- |
|  **minimal**  |  ✅   |    ✅     |      ❌      |   ❌    | Quick status check   |
| **executive** |  ✅   |    ✅     |      ✅      |   ❌    | Leadership (default) |
| **detailed**  |  ✅   |    ✅     |      ✅      |   ✅    | Technical deep dive  |

---

## 🔐 API token setup

Create a read-only API token in Cloudflare Dashboard → **Manage Account** → **Account API Tokens**

### Required permissions

| Permission                        | Required        |
| --------------------------------- | --------------- |
| Zone > Zone Read                  | ✅ Yes          |
| Zone > Analytics Read             | ✅ Yes          |
| Zone > DNS Read                   | ⚠️ Recommended  |
| Zone > SSL and Certificates Read  | ⚠️ Recommended  |
| Zone > Zone Settings Read         | ⚠️ Recommended  |
| Zone > Firewall Services Read     | ⚠️ Recommended  |
| Zone > WAF Read                   | ⚠️ Recommended  |
| Account > Access: Audit Logs Read | ℹ️ Nice-to-have |
| Account > Account Settings Read   | ℹ️ Nice-to-have |

> **✅ Required** = Tool won't work | **⚠️ Recommended** = Full features | **ℹ️ Nice-to-have** = Better validation

### Quick validation

```bash
# Shows exactly which permissions you have
cf-report validate
```

### Security notes

- 🔒 **Read-only only** - The tool never needs write permissions
- 💾 **All data stays local** - Cached in `~/.cf-report/`, no telemetry
- 📖 **[Full security guide →](SECURITY.md)** - Step-by-step token creation, data storage details, and security checklist

---

## 📈 How scoring works

**Only `risk` takeaways affect your score.** Everything else (`win`, `action`, `comparison`, `observation`) is informational.

```txt
Score = max(0, 100 - (total_risk_weight / 60) * 100)
```

| Risk weight | Score | Grade | Example                         |
| ----------- | ----- | ----- | ------------------------------- |
| 0           | 100   | A+    | No risks found                  |
| 19          | 68    | C+    | SSL off (10) + WAF disabled (9) |
| 26          | 57    | C     | Three medium risks              |
| 60+         | 0     | F     | Critical security gaps          |

---

## ⏱️ Data retention (by Cloudflare plan)

| Plan       | DNS | Security | HTTP |
| ---------- | --- | -------- | ---- |
| Free       | 7d  | 7d       | 30d  |
| Pro        | 31d | 7d       | 30d  |
| Business   | 31d | 31d      | 30d  |
| Enterprise | 62d | 90d      | 30d  |

> Days outside these windows = `unavailable` (cached, no API calls)

---

## ⚙️ Quick config (`~/.cf-report/config.yaml`)

```yaml
api_token: "cfat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
cache_dir: "~/.cf-report/cache"
history_dir: "~/.cf-report/history"
log_level: "info"

zones:
  - id: "abc123..."
    name: "example.com"

pdf:
  profile: "executive" # minimal | executive | detailed
  chart_format: "png" # png | svg
  map_format: "png" # png | svg
  colors:
    primary: "#2563eb" # your brand color
    accent: "#f38020"

email:
  enabled: true
  smtp_host: "smtp.example.com"
  recipients:
    - "security@example.com"
```

---

## 🛠️ CLI cheat sheet

```bash
# Sync data
cf-report sync --last 30                    # Last 30 days
cf-report sync --zone example.com --last 7  # Single zone

# Generate report
cf-report report -o report.pdf              # Basic PDF
cf-report report -o report.pdf --email      # PDF + email
cf-report report --skip-zone-health         # Skip health checks

# Manage zones
cf-report zones list
cf-report zones add --id abc123 --name example.com

# Clean cache
cf-report clean --older-than 90
```

---

## 📚 Documentation

| Guide                                                         | What it covers                  |
| ------------------------------------------------------------- | ------------------------------- |
| [User guide](docs/USAGE.md)                                   | Full CLI reference and config   |
| [Dashboard verification](docs/verify-report-vs-cloudflare.md) | Compare report vs Cloudflare UI |
| [Reliability metrics](docs/reliability-metrics.md)            | Understanding approximations    |
| [Developer docs](docs/developers/)                            | Architecture and internals      |

---

## ❓ Common questions

**How accurate are the metrics?**
Trend-oriented approximations. Use for executive posture guidance, not packet-level forensics.

**Can I run this in CI/CD?**
Yes - works headless. Set `CF_REPORT_API_TOKEN` (preferred) and pass `--config` to a non-secret config file.

**What if I have 100+ zones?**
Works fine. Sync may take a while initially, but caching helps.

---

## 📦 Links

- [PyPI](https://pypi.org/project/cloudflare-executive-report/)
- [GitHub](https://github.com/vhsantos/cloudflare-executive-report)
- [Issues](https://github.com/vhsantos/cloudflare-executive-report/issues)

---

## 📄 License

MIT - go wild. See [LICENSE](LICENSE).
