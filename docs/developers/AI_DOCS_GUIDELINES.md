# Documentation Style Guide

## Core principle: Know your reader

|                        | **End User**                                 | **Developer**                               |
| ---------------------- | -------------------------------------------- | ------------------------------------------- |
| **Goal**               | "Can I use this?"                            | "How does this work?"                       |
| **Mindset**            | Impatient, task-oriented                     | Curious, architecture-oriented              |
| **Wants**              | Quick wins, clear value, copy-paste commands | Edge cases, extension points, failure modes |
| **Doesn't care about** | Internal design patterns, class hierarchies  | Marketing language, emojis                  |

---

## Section ordering: The inverted pyramid

### For End User READMEs

```txt
1. Name + one-liner (what)
2. Why this exists (problem statement)
3. What you get (features as benefits, not implementation)
4. See it in action (screenshots or sample outputs)
5. Quick start (30 seconds to success)
6. Core concepts (only what they need to make decisions)
7. Configuration reference
8. FAQ (real questions, not invented ones)
9. Links
```

### For Developer docs (CONTRIBUTING.md, ARCHITECTURE.md)

```txt
1. Prerequisites (dependencies, versions)
2. Project structure (where things live)
3. Setup from source
4. Key design decisions (why it's built this way)
5. Testing strategy
6. Adding new features (extension patterns)
7. Debugging guide
8. Release process
```

### ASCII Text

* Do not use — or “ ”, use - and " for example.
* Do not forgot to add the correct type on the blocks, like:

```txt
```

```python
```

```markdown
```

---

## Visual hierarchy rules

### Use emojis strategically (end user only)

| Purpose             | Emoji                                             | Use case                        |
| ------------------- | ------------------------------------------------- | ------------------------------- |
| Section anchor      | 🎯 🚀 ✨ 📊                                       | Visual scanning, not decoration |
| Status indicator    | ✅ ❌ ⚠️ 🔒                                       | Quick comprehension             |
| File/command prefix | 📄 📁 💻                                          | Differentiate from prose        |
| **Never use**       | Overlapping emojis, 3+ per line, as bullet points | Creates noise                   |

### Tables: When and how

**Use tables for:**

- Feature comparisons (✅/❌)
- Permission mappings
- Plan/retention matrices
- CLI command summaries

**Avoid tables for:**

- Narrative explanations
- Single column of data (use a list)
- More than 5 columns (horizontal scroll hell)

**Alignment rules:**

```markdown
| Left     |         Center          |       Right |
| :------- | :---------------------: | ----------: |
| Use :--- |        Use :---:        |    Use ---: |
| For text | For icons/short strings | For numbers |
```

### Code blocks: Language matters

````markdown
# Good - specifies language for syntax highlighting

```bash
cf-report sync --last 30
```
````

# Bad - no language

```
cf-report sync --last 30
```

````

---

## Tone and voice

| Element | End User | Developer |
|---------|----------|-----------|
| Pronouns | "You" (direct) | "The system" (neutral) |
| Sentence length | Short (15-20 words) | Variable (can be longer) |
| Emojis | Yes, sparingly | No |
| Contractions | Yes ("it's", "you'll") | Optional |
| Callouts | "That's it." "You're done." | None |
| Humor | Very sparing, professional | No |

**Example of the difference:**

> **End user:** "Run this command and you'll have your first report in seconds."
>
> **Developer:** "The `sync` command fetches data from the Analytics GraphQL API and stores it locally as Parquet files."

---

## The "Quick start" formula

A good quick start has exactly **4-6 steps** and takes **30 seconds or less** to read:

```markdown
## 🚀 Quick start (30 seconds)

```bash
pip install tool-name
tool init          # prompts for API key
tool sync --last 7
tool run -o output.pdf
````

That's it. You just [did the thing].

````

**Rules:**
- Every command must work if copy-pasted sequentially
- No hidden prerequisites (if needed, state before the code block)
- First command = install
- Last command = visible output or file creation
- Celebrate the success (one line max)

---

## Callout boxes

```markdown
> ⚠️ **Warning:** This operation cannot be undone.

> 📝 **Note:** SVG rendering increases file size significantly.

> 💡 **Tip:** Use `--skip-zone-health` for faster runs without settings checks.

> 🔐 **Security:** Never commit your `config.yaml` with API tokens.
````

---

## The "Problem → Solution" table (end user gold)

Convert feature lists into user problems:

```markdown
| Problem                             | Solution                              |
| ----------------------------------- | ------------------------------------- |
| 📅 Dashboard only shows recent data | Historical windows beyond convenience |
| 🌍 One zone at a time               | One report across many zones          |
```

**Why it works:** Users don't care about your features. They care about their pain.

---

## Screenshots and examples placement

| Content                  | Where                | Why                  |
| ------------------------ | -------------------- | -------------------- |
| Sample output (PDF/HTML) | After "What you get" | Prove the promise    |
| CLI output example       | After the command    | Set expectations     |
| Architecture diagram     | Developer docs only  | End users don't care |
| Configuration file       | Reference section    | Search, don't read   |

---

## Accessibility guidelines

- **Don't rely solely on color** - use icons or text labels
- **Table headers required** - screen readers need them
- **Link text is descriptive** - "See [User Guide](link)" not "Click here"
- **Code blocks have language** - helps screen readers and syntax highlighting

---

## Checklist before publishing

### End User README

- [ ] Can someone copy-paste the quick start and succeed?
- [ ] Does the first screen (no scroll) answer "what" and "why"?
- [ ] Are all external links working?
- [ ] Is there at least one visual (emoji, badge, or screenshot)?
- [ ] Would you use this tool after reading it?

### Developer docs

- [ ] Can someone build from source using only this doc?
- [ ] Are all failure modes documented?
- [ ] Is the testing strategy explained?
- [ ] Are extension points clearly marked?
- [ ] Would you feel confident submitting a PR?

---

## Examples of good vs bad

### ❌ Bad (developer thinking for end user)

> "The CloudflareExecutiveReport class instantiates a PDF renderer with configurable output profiles. Call `generate()` to produce the report object."

### ✅ Good (end user thinking)

> "Run `cf-report report -o report.pdf` and get a security PDF ready for your leadership team."

### ❌ Bad (end user thinking for developer)

> "First, install the tool. Then run init. Then sync. Then report. It's easy!"

### ✅ Good (developer thinking)

> "Data flows: Analytics API → Parquet cache → Risk engine → PDF renderer. Each stage is pluggable via `interfaces.py`."

---

## One-page cheat sheet

```markdown
# README Cheat Sheet (End User)

1. **Name + badge row**
2. **One-liner** - "Turn X into Y"
3. **Why this exists** - Problem/solution table
4. **What you get** - Features as benefits (emoji + short)
5. **See it in action** - Links to examples (no long descriptions)
6. **Quick start** - 4-6 copy-paste commands
7. **Core decisions** - Tables with ✅/❌ comparisons
8. **Reference** - Config, CLI, FAQ
9. **Links + license**

**Golden rule:** Every section answers "why should I keep reading?"
```

---

## AI prompt template

Copy and paste this when asking an AI to write documentation:

```
Write documentation for [TOOL NAME] following these rules:

**Audience:** [End User / Developer]

**Structure:**
- Start with a one-liner and badges
- Add a "Why this exists" problem/solution table
- List "What you get" as benefits (not features)
- Show "Quick start" with 4-6 copy-paste commands
- Use tables for comparisons, lists for sequences
- Add emojis only for end user docs (🎯 🚀 ✨ 📊)
- End with FAQ and links

**Tone:** [Confident, professional, concise / Technical, precise, neutral]

**Constraints:**
- No hidden prerequisites
- Every command must work if copy-pasted
- No paragraphs longer than 3 sentences
- Use callouts (>, > ⚠️, > 💡) for notes

**Format:** Markdown
```

---

## License

This guide is free to use, modify, and share. No attribution required.
