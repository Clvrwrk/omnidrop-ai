# OmniDrop AI — Third-Party Service Reference Docs

This directory contains one reference doc per external service. Every agent reads the relevant doc before touching code that calls that service.

---

## Index

| Service | File | Used By | Status |
|---|---|---|---|
| Supabase | [supabase.md](supabase.md) | All agents — DB, Storage, RLS | ☐ |
| Voyage AI | [voyage-ai.md](voyage-ai.md) | AI & QA — embeddings | ☐ |
| Unstructured.io | [unstructured.md](unstructured.md) | AI & QA — document parsing | ☐ |
| Hookdeck | [hookdeck.md](hookdeck.md) | Backend Plumber — webhook gateway | ☐ |
| Sentry | [sentry.md](sentry.md) | All agents — error tracking | ☐ |
| WorkOS | [workos.md](workos.md) | Frontend + Backend — auth | ☐ |
| Render | [render.md](render.md) | Lead — deployment | ☐ |
| AccuLynx | [acculynx.md](acculynx.md) | Backend Plumber — integration partner | ☐ |
| Cron / Scheduling | [cronjob.md](cronjob.md) | Lead — future maintenance tasks | ☐ |
| ServiceTitan | [servicetitan.md](servicetitan.md) | Future integration (reference only) | ☐ |
| JobNimbus | [jobnimbus.md](jobnimbus.md) | Future integration (reference only) | ☐ |
| JobTread | [jobtread.md](jobtread.md) | Future integration (reference only) | ☐ |

---

## How to Use These Docs

1. **Before writing any code** that touches an external service, read its reference doc first.
2. **Tool preference order:** MCP tools → CLI → Direct API. Use the highest available tier.
3. **Human SOPs** are the only way to do things Claude cannot automate. Follow them exactly.
4. **After completing a SOP**, use the exact resume message at the end to tell Claude to continue.

---

## Standard File Format

Every reference doc in this directory follows this exact structure. Do not deviate.

---

```markdown
# [Service Name] — OmniDrop Reference

## 1. What It Does Here
[Why OmniDrop uses it. Which files/tasks touch it. One paragraph max.]

## 2. Credentials & Environment Variables

| Variable | Where to Find It | Used By |
|---|---|---|
| `VAR_NAME` | [Dashboard URL or location] | backend / frontend / worker |

## 3. CLI
[Install command. Auth command. Key operational commands — copy-paste ready. Debug commands.]

```bash
# Install
npm install -g [tool]

# Auth
[tool] login

# Key commands
[tool] [command] --flag value
```

## 4. MCP (Claude Code)
[Available MCP tools for this service. Preferred tool per operation. Example calls.]

| Operation | Preferred Tool | Example |
|---|---|---|
| [operation] | `mcp__[tool]__[method]` | `{ "param": "value" }` |

## 5. Direct API
[Base URL. Auth header. Key endpoints with curl examples.]

```bash
curl -X GET "https://api.example.com/v1/resource" \
  -H "Authorization: Bearer $API_KEY"
```

## 6. OmniDrop-Specific Patterns
[Exact file paths + function names. Rate limits. Known gotchas. Copy-paste code patterns.]

## 7. ⛔ Human SOP

### SOP-[SERVICE]-[N]: [Task Name]
**When:** [Trigger — what causes this step to be needed]
**Time:** ~[X] minutes
**Prerequisite:** [What must be true first]

Step 1. Go to [exact URL]
Step 2. Click **[exact button label]** in [exact location]
Step 3. In the field **"[exact field name]"**, enter: `[exact value or format]`
Step 4. Copy the value labeled **"[exact label]"** — it looks like: `[example]`
Step 5. Paste into `[exact file path]` as `[VARIABLE_NAME]=...`
Step 6. Tell Claude: `"[exact resume message]"`

✅ Done when: [Observable outcome]
⚠️ If you see `"[error message]"`: [exact recovery step]
```

---

## Resume Message Convention

Every Human SOP must end with a resume message in this format:

```
"[Service] SOP-[N] complete. [Variable name] is set. Resume [task name]."
```

Example:
```
"Supabase SOP-1 complete. SUPABASE_SERVICE_ROLE_KEY is set. Resume T1-01 RLS migration."
```
