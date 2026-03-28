---
name: Claude Skills Reference
description: Complete reference for all skills available at github.com/anthropics/skills — what each skill does, when it triggers, and how to add missing ones
type: reference
---

# Claude Skills Reference
**Source:** https://github.com/anthropics/skills
**Spec:** https://agentskills.io/specification
**Last reviewed:** 2026-03-27

---

## How Skills Work

A skill is a directory containing a `SKILL.md` file (+ optional `scripts/`, `references/`, `assets/`).

### SKILL.md Frontmatter Fields

| Field | Required | Notes |
|-------|----------|-------|
| `name` | Yes | Max 64 chars. Lowercase + hyphens only. Must match directory name. |
| `description` | Yes | Max 1024 chars. Include WHAT it does AND WHEN to trigger. |
| `license` | No | e.g. `Apache-2.0` |
| `compatibility` | No | Max 500 chars. e.g. `Requires Python 3.14+` |
| `metadata` | No | Key-value map for extra info |
| `allowed-tools` | No | Space-delimited pre-approved tools (experimental) |

### Loading Strategy (Progressive Disclosure)
1. `name` + `description` → loaded at startup for ALL skills (~100 tokens each)
2. Full `SKILL.md` body → loaded when skill is **activated** (<5000 tokens recommended, max 500 lines)
3. Files in `scripts/`, `references/`, `assets/` → loaded **on demand**

### How to Add a Missing Skill
```bash
# Install via Claude Code plugin marketplace
/plugin marketplace add anthropics/skills
/plugin install <skill-name>@anthropic-agent-skills
```

Or manually: clone the skill folder into your project and reference it.

---

## All 17 Official Anthropics Skills

### 1. `algorithmic-art`
**Triggers:** User requests generative/algorithmic art, flow fields, particle systems, code-based art
**Does:** Creates a "Design Philosophy" `.md` + self-contained interactive HTML with p5.js, seeded randomness, parameter sliders, seed nav
**Key files:** `templates/viewer.html` (fixed structure — only algorithm section changes)

---

### 2. `brand-guidelines`
**Triggers:** Brand colors, style guidelines, visual formatting, company design standards
**Does:** Applies Anthropic brand colors + typography to any artifact
**Palette:** Dark `#141413`, Light `#faf9f5`, Orange `#d97757`, Blue `#6a9bcc`, Green `#788c5d`
**Typography:** Poppins (headings 24pt+), Lora (body)

---

### 3. `canvas-design`
**Triggers:** Create a poster, piece of art, design, or static visual piece
**Does:** Creates Design Philosophy `.md` + executes as `.pdf`/`.png` via Python (matplotlib, PIL, reportlab)
**Key:** Two-pass refinement (create → mandatory polish). Fonts from `./canvas-fonts/`

---

### 4. `claude-api`
**Triggers:** Code imports `anthropic`/`@anthropic-ai/sdk`/`claude_agent_sdk`; user asks to use Claude API or Anthropic SDKs
**Does NOT trigger for:** `openai` or other AI SDKs
**Does:** Detects project language, reads language-specific docs, covers API calls, streaming, tool use, batches, Files API, Agent SDK
**Defaults:** Model = `claude-opus-4-6`, adaptive thinking, streaming for long requests
**Key:** `budget_tokens` deprecated on Opus 4.6/Sonnet 4.6

---

### 5. `doc-coauthoring`
**Triggers:** User wants to write docs, proposals, technical specs, PRDs, RFCs, decision docs
**Does:** 3-stage workflow: Context Gathering → Refinement & Structure → Reader Testing
**Key:** Always `str_replace` for edits — never reprint whole doc. Sub-agent reader test at end.

---

### 6. `docx`
**Triggers:** "Word doc," ".docx," reports/memos/letters/templates as Word files, tracked changes
**Does NOT trigger for:** PDFs, spreadsheets, Google Docs
**Does:** Read via `pandoc` or `unpack.py`; create with `docx` npm package (JS); edit via XML unpack → Edit tool → repack
**Key gotchas:** Never `\n` (use Paragraphs); never `WidthType.PERCENTAGE`; `LevelFormat.BULLET` not unicode bullets; `ShadingType.CLEAR` not SOLID

---

### 7. `frontend-design`
**Triggers:** Build web components, pages, artifacts, landing pages, dashboards, React components, HTML/CSS layouts, styling/beautifying web UI
**Does:** Bold aesthetic direction first (brutalist, retro-futuristic, luxury, etc.), then distinctive code
**Key:** NEVER generic AI aesthetics (no purple gradients, no Inter/Roboto, no centered-everything)

---

### 8. `internal-comms`
**Triggers:** Status reports, leadership updates, 3P updates, newsletters, FAQs, incident reports
**Does:** Identifies comm type → loads matching guideline from `examples/` (`3p-updates.md`, `company-newsletter.md`, `faq-answers.md`, `general-comms.md`)

---

### 9. `mcp-builder`
**Triggers:** Building MCP servers to integrate external APIs or services
**Does:** 4-phase workflow: Research → Implement → Review/Test → Evaluations
**Key:** TypeScript recommended. Streamable HTTP for remote, stdio for local. Creates 10 QA eval pairs.

---

### 10. `pdf`
**Triggers:** Any mention of `.pdf` file or request to produce one
**Does:** Read (`pdfplumber`, `pypdf`), create (`reportlab`), OCR (`pytesseract`+`pdf2image`), forms (pdf-lib/pypdf)
**Key:** Never Unicode sub/superscript — use `<sub>`/`<super>` XML tags in Paragraph objects

---

### 11. `pptx`
**Triggers:** `.pptx` file, create/read/edit slide decks, pitch decks, "deck"/"slides"/"presentation"
**Does:** Read via `markitdown`; edit via unpack XML → repack; create via `pptxgenjs` npm package
**Key:** Mandatory visual QA via LibreOffice → images after every creation/conversion

---

### 12. `skill-creator`
**Triggers:** Create a new skill, edit/optimize existing skill, run evals, benchmark skill performance
**Does:** Iterative loop: draft SKILL.md → test prompts → evaluate → rewrite → repeat
**Key:** Quantitative evals via `eval-viewer/generate_review.py`

---

### 13. `slack-gif-creator`
**Triggers:** Requests for animated GIFs for Slack
**Does:** Uses `GIFBuilder` class with easing functions, frame composers. Produces emoji (128×128) or message (480×480) GIFs
**Deps:** `pip install pillow imageio numpy`. Never use emoji fonts.

---

### 14. `theme-factory`
**Triggers:** User wants consistent visual styling applied to any artifact
**Does:** Shows `theme-showcase.pdf` → user picks theme → applies from `themes/` directory
**10 themes:** Ocean Depths, Sunset Boulevard, Forest Canopy, Modern Minimalist, Golden Hour, Arctic Frost, Desert Rose, Tech Innovation, Botanical Garden, Midnight Galaxy
**Custom:** Generates new theme on-the-fly if none fit.

---

### 15. `web-artifacts-builder`
**Triggers:** Complex artifacts needing state management, routing, or shadcn/ui components
**Does NOT trigger for:** Simple single-file HTML/JSX
**Does:** Scaffolds React 18 + TypeScript + Vite + Tailwind 3.4.1 + 40+ shadcn/ui components → bundles to single `bundle.html`

---

### 16. `webapp-testing`
**Triggers:** Verify frontend functionality, debug UI, capture browser screenshots, view browser logs
**Does:** Native Python Playwright scripts. `scripts/with_server.py` manages server lifecycle.
**Key:** Always headless Chromium. Always `wait_for_load_state('networkidle')` before DOM inspection.

---

### 17. `xlsx`
**Triggers:** Open/read/edit/create `.xlsx`, `.xlsm`, `.csv`, `.tsv`; deliverable must be a spreadsheet
**Does NOT trigger for:** Word docs, HTML reports, standalone scripts, Google Sheets API
**Does:** `pandas` for analysis/bulk ops; `openpyxl` for formulas/formatting
**Key:** ALWAYS use Excel formulas (not Python-calculated values). MANDATORY `scripts/recalc.py` after formula work. Zero formula errors required.

---

## Quick Lookup: Skill by Task

| Task | Skill |
|------|-------|
| Generative/algorithmic art with p5.js | `algorithmic-art` |
| Apply Anthropic brand colors/fonts | `brand-guidelines` |
| Create poster/artwork as PNG/PDF | `canvas-design` |
| Use Claude API / Anthropic SDK | `claude-api` |
| Write documentation collaboratively | `doc-coauthoring` |
| Create/edit Word (.docx) files | `docx` |
| Design web UI / React components | `frontend-design` |
| Write status reports / newsletters | `internal-comms` |
| Build an MCP server | `mcp-builder` |
| Anything with PDF files | `pdf` |
| Create/edit PowerPoint (.pptx) | `pptx` |
| Build or improve a skill | `skill-creator` |
| Make animated GIFs for Slack | `slack-gif-creator` |
| Apply visual themes to artifacts | `theme-factory` |
| Complex multi-component web artifacts | `web-artifacts-builder` |
| Test/screenshot local web apps | `webapp-testing` |
| Create/edit spreadsheets (.xlsx/.csv) | `xlsx` |

---

## Creating a Custom Skill (Minimal Template)

```markdown
---
name: my-skill-name
description: Does X, Y, Z. Use when the user asks for [specific triggers].
---

# My Skill

## When to Use
- Trigger condition 1
- Trigger condition 2

## Instructions
Step-by-step instructions here...
```

Validate with: `skills-ref validate ./my-skill`
