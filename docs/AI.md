# 🤖 AI-Powered Executive Summary

> Optional LLM-generated one-paragraph summaries from multi-zone portfolio data. Because CTOs have zero time to read dashboards.

[![Optional Feature](https://img.shields.io/badge/feature-optional-orange.svg)](README.md#ai-summary)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-blue.svg)](https://openrouter.ai/)
[![AI: Powered by LLMs (Optional)](https://img.shields.io/badge/AI-powered-brightgreen.svg)](AI.md)

---

## 🎯 Why AI? (The real story)

![Cartoon-style illustration showing the evolution of CTO feedback.](images/ai-cto-evolution.webp)

> I sent the first report to a CTO "friend" and he told me **_"way too much information"_** and to **_"stop wasting my time with 50 detailed pages"_**.🤷 So we added a per‑zone executive summary. He got the new report and replied **_"still too much"_**. Then we built a single‑page portfolio with just the takeaways and actions for all zones. Sent it to him, but he never replied. 😭
>
> At that point I realized: **_the report wasn't the problem._** 🤷 So now we feed the portfolio into an LLM and, at the end, it spits out just one line:
>
> ✅ **"Everything is fine"** _or_ 💀 **"We're screwed"**
>
> Will this be short enough for any CTO? Will they finally read it?
>
> Let's be honest — the email will probably stay unopened. 😄

---

## ✨ What the AI delivers

| What you get                    | What you don't get                      |
| ------------------------------- | --------------------------------------- |
| 1‑2 paragraph executive summary | ❌ Markdown, tables, or bullet points   |
| Emergency stated first (if any) | ❌ "I", "we", or "you" pronouns         |
| Single most critical action     | ❌ Zone names, domains, or IP addresses |
| Clear recommendation at the end | ❌ Anything exceeding 250 words         |
| Under 250 words                 | ❌ Technical deep‑dive or raw numbers   |

---

## 📊 What Data Is Sent to the LLM

The AI only receives **aggregated, zone‑agnostic** data from the portfolio:

```text
Multi-Zone Security Summary

Grade distribution:
  C (55-64): 3 zones

Total zones evaluated: 3

Common risks (count of zones affected):
  - Web Application Firewall disabled - no attack protection (WAF-001): 3 zones
  - DNSSEC disabled - domain spoofing risk (DNS-001): 2 zones
  - DMARC policy is None. Attackers can send email as your domain. (EMAIL-001): 2 zones
  - DKIM missing. Outbound email authenticity cannot be verified. (EMAIL-007): 1 zone
  - HSTS disabled - HTTPS not enforced. Visitors may connect over insecure HTTP. (TLS-006): 1 zone

Actions required:
  - [WAF-001] Review and remediate: Web Application Firewall disabled
  - [DNS-001] Review and remediate: DNSSEC disabled
  - [EMAIL-001] Review and remediate: DMARC policy is None
  - [EMAIL-007] Review and remediate: DKIM missing
  - [TLS-006] Review and remediate: HSTS disabled
```

### ✅ Sent to the model

- Grade distribution (counts only, no zone names)
- Risk count per check (WAF disabled in **X** zones)
- Actionable remediation steps

### ❌ NOT sent to the model

- Zone names, domains, or IP addresses
- Individual zone scores or grades
- Raw HTTP/DNS/Security metrics
- Any PII or customer identifiers
- Geographic locations

---

## 🎚️ How to Enable AI Summaries

AI summaries are **disabled by default**. Enable them in your `~/.cf-report/config.yaml`:

```yaml
ai_summary:
  enabled: true # Turn it on
  model: "openrouter/meta-llama/llama-3.2-3b-instruct:free" # Optional: override default
```

That's it. Keep it simple.

### 🔧 System defaults (hardcoded, not in user config)

| Setting             | Default value                                                                                                                                                                   | Why                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| **Primary model**   | `openrouter/meta-llama/llama-3.2-3b-instruct:free`                                                                                                                              | Fast, non‑reasoning, good for summaries |
| **Fallback models** | `openrouter/google/gemma-2-9b-it:free`<br>`openrouter/microsoft/phi-3.5-mini-128k-instruct:free`<br>`openrouter/qwen/qwen-2.5-7b-instruct:free`<br>`openrouter/openrouter/free` | Automatic retry if rate‑limited         |
| **Max tokens**      | 1500                                                                                                                                                                            | Enough for 250‑word summary             |
| **Temperature**     | 0.3                                                                                                                                                                             | Consistent, non‑creative output         |
| **Timeout**         | 30 seconds                                                                                                                                                                      | Fail fast, move to fallback             |

> **Note**: Fallback models and token limits are **not** user‑configurable. They're baked into the code to keep your config clean.

---

## 🔐 API Key Setup (Required)

Even free OpenRouter models require an API key for rate limiting.

### Option 1: Environment variable (recommended)

```bash
export OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### Option 2: Config file (not recommended for CI/CD)

```yaml
ai_summary:
  enabled: true
  api_key: "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

> Priority: `OPENROUTER_API_KEY` env var → `OPENAI_API_KEY` env var → config file `api_key`

### Get your free API key

1. Go to [OpenRouter Keys](https://openrouter.ai/keys)
2. Sign up (free tier available)
3. Create a key
4. The free tier includes rate‑limited access to models like Llama, Gemma, and Phi

---

## 🧪 Validate AI Setup

```bash
# Run with verbose logging to see AI output
cf-report -v report --start 2026-04-27 --end 2026-04-28 -o report.pdf --ai-summary

# Expected output when successful
INFO AI summary generated successfully using model: openrouter/meta-llama/llama-3.2-3b-instruct:free

================================================================================
                         AI-Generated Executive Summary
================================================================================
Critical security gaps exist across all evaluated zones, with a universal
  failure to implement Web Application Firewall protections. The most critical
  action required is the immediate activation and configuration of Web
  Application Firewalls across all zones...
================================================================================
```

---

## ⚙️ How It Works (Behind the Scenes)

```mermaid
flowchart LR

%% ---------- STYLES ----------
classDef cli fill:#1f2937,color:#fff,stroke:#111;
classDef ai fill:#7c3aed,color:#fff,stroke:#5b21b6;

%% ---------- NODES ----------
PORTFOLIO[Portfolio Summary]
PROMPT[Build Prompt]
MODEL1[Model 1: Primary]
MODEL2[Model 2: Fallback]
LLM[OpenRouter API]
RESULT[Executive Summary]

%% ---------- FLOWS ----------
PORTFOLIO --> PROMPT
PROMPT --> MODEL1
MODEL1 -->|Rate limited/error| MODEL2
MODEL2 --> LLM
LLM --> RESULT

%% ---------- CLASSES ----------
class PORTFOLIO,PROMPT,RESULT cli
class MODEL1,MODEL2,LLM ai
```

1. **Portfolio summary** is built from multi‑zone scan (no PII)
2. **System prompt** + **user prompt** are assembled
3. **Primary model** is called via litellm → OpenRouter
4. On rate limit/error, **fallback models** are tried with 2‑second delays
5. **Content extraction** handles both reasoning and non‑reasoning models
6. **Summary is printed** to terminal (and optionally included in email)

---

## 🚫 What Happens When Things Fail

| Failure mode                | Behavior                                     | User impact                       |
| --------------------------- | -------------------------------------------- | --------------------------------- |
| litellm not installed       | Warning logged, no AI summary                | Install `pip install ...[ai]`     |
| Rate limit (429)            | Automatic fallback to next model (2s delay)  | Slightly slower, but still works  |
| All models fail             | Error logged, PDF still generated            | PDF works, AI summary missing     |
| API key missing/invalid     | Authentication error, fallback to next model | Try next model or fail gracefully |
| Model returns empty content | Warning logged, move to next fallback        | Next model is tried               |

> **Important**: AI summary generation **never blocks PDF creation**. If AI fails, you still get your report.

---

## 📊 Example AI Output

**Input portfolio** (3 zones, all grade C, WAF disabled everywhere):

**AI‑generated summary**:

> _Critical security gaps exist across all evaluated zones, with a universal failure to implement Web Application Firewall protections. This systemic absence of attack protection leaves the entire environment vulnerable to common web‑based exploits. Additional aggregate risks include widespread deficiencies in DNS security and email authentication protocols, increasing the likelihood of domain spoofing and unauthorized email impersonation._
>
> _The most critical action required is the immediate activation and configuration of Web Application Firewalls across all zones. Secondary priority must be given to hardening DNS and email security policies to prevent external impersonation. It is recommended to mandate a standardized security baseline across all zones to eliminate these recurring vulnerabilities._

---

## ❓ Common Questions

**Does this send my zone data to external servers?**
Yes – the prompt (aggregated, zone‑agnostic data) is sent to OpenRouter's API. No zone names, domains, or IP addresses are included. See [What Data Is Sent](#-what-data-is-sent-to-the-llm).

**Can I use my own OpenAI/Gemini API key instead?**
Yes – set `OPENAI_API_KEY` or `OPENROUTER_API_KEY`. The tool uses whatever key matches the model provider.

**Why am I getting rate limit errors?**
Free tier models have aggressive rate limits. The tool automatically retries with fallback models and 2‑second delays.

**Can I disable AI summaries?**
Yes – set `ai_summary.enabled: false` in your config (it's disabled by default).

**What if I don't want any AI at all?**
Just don't enable it. The tool works perfectly without the `ai` extra installed.

---

## 🔧 Troubleshooting

### AI summary not showing

```bash
# Check if AI is enabled
grep -A2 "ai_summary" ~/.cf-report/config.yaml

# Run with verbose logging
cf-report -vv report -o test.pdf --ai-summary

# Check litellm installation
pip list | grep litellm
```

### Rate limit errors

```bash
# Expected output when rate‑limited
WARNING Model openrouter/google/gemma-4-31b-it:free failed because "rate limited", trying next fallback
WARNING Model openrouter/meta-llama/llama-3.3-70b-instruct:free failed because "rate limited", trying next fallback
INFO AI summary generated successfully using model: openrouter/nvidia/nemotron-3-super-120b-a12b:free
```

### Installation issues

```bash
# Install with AI extras
pip install 'cloudflare-executive-report[ai]'

# Or install manually
pip install litellm
```

---

## 📚 Related Documentation

- [User Guide](docs/USAGE.md) - Full CLI reference
- [OpenRouter Documentation](https://openrouter.ai/docs)
- [litellm Documentation](https://docs.litellm.ai/)

---

⬅️ [Back to README](README.md) | [Security Guide →](SECURITY.md)
