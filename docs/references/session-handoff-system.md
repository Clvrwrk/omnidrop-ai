# Session Handoff System — OmniDrop Reference

## What This Is

A protocol that treats every Claude session like a work shift. At 50% context usage, Claude drafts a comprehensive handoff document and stops. When a new session starts, `/ProjectHandoff` reads that document and resumes as if the session never ended.

**Goal:** Zero information loss between sessions. No re-explaining context. No guessing what was in progress.

---

## How It Works

```
During Session
  │
  ├── [context < 50%] → work normally
  │
  └── [context hits 50%]
        │
        ├── 1. Finish current function/block (never stop mid-code)
        ├── 2. Commit all changes
        ├── 3. Write docs/handoffs/current.md
        ├── 4. Archive to docs/handoffs/archive/YYYY-MM-DD-HHMM.md
        ├── 5. Notify user: "🟡 CONTEXT 50% — Handoff written. /ProjectHandoff to resume."
        └── 6. STOP — do not start next task

New Session
  │
  └── User types: /ProjectHandoff
        │
        ├── 1. Read docs/handoffs/current.md
        ├── 2. Announce summary (what's done, what's next, any blockers)
        ├── 3. Confirm first task with user
        └── 4. Begin immediately
```

---

## File Locations

| File | Purpose |
|---|---|
| `docs/handoffs/current.md` | Always the latest handoff — overwritten each time |
| `docs/handoffs/archive/YYYY-MM-DD-HHMM.md` | Full history — never deleted |

---

## The /ProjectHandoff Command

Type `/ProjectHandoff` at the start of any session to resume.

Claude will:
1. Read `docs/handoffs/current.md`
2. Show a one-screen summary (completed, in progress, next task, blockers)
3. Ask which task to start
4. Begin immediately

**You do not need to explain anything.** The handoff document contains everything Claude needs.

---

## ⛔ Human SOP — What You Need to Do

### SOP-HANDOFF-1: Starting a New Session After a Handoff
**When:** Any time you open a new Claude Code session and there's in-progress work
**Time:** ~30 seconds

Step 1. Open Claude Code in the OmniDrop AI project directory
Step 2. Type exactly: `/ProjectHandoff`
Step 3. Read Claude's summary — confirm the next task is correct
Step 4. Type "yes" or "start" to begin, OR tell Claude which task to prioritize instead

✅ Done when: Claude begins working on the confirmed task
⚠️ If Claude says "No handoff document found": Type "check docs/ for project context" — Claude will orient from the spec files instead

---

### SOP-HANDOFF-2: Forcing an Early Handoff
**When:** You need to end a session before context hits 50%
**Time:** ~1 minute

Step 1. Tell Claude: "Generate a handoff document now — I need to end this session"
Step 2. Wait for Claude to finish the current function and commit
Step 3. Confirm handoff is written: Claude will say "Handoff written to docs/handoffs/current.md"
Step 4. Close the session

✅ Done when: Claude sends the 🟡 CONTEXT 50% message (even if triggered manually)

---

### SOP-HANDOFF-3: Checking What Was Last Worked On
**When:** You're not sure what's in progress without starting a session
**Time:** ~1 minute

Step 1. Open a Finder window
Step 2. Navigate to: Desktop → Claude Setup - Standard → Projects → OmniDropAI → docs → handoffs
Step 3. Open `current.md` in any text editor
Step 4. Read "Next Task — Start Here" section

✅ Done when: You can see the next task without opening Claude Code

---

## When Handoffs Are Most Critical

1. **Mid-implementation** — Any endpoint or page that's half-built
2. **Mid-migration** — Never leave a migration half-applied
3. **After a decision** — Decisions not captured in code must go in the handoff
4. **Before a Human SOP step** — Always handoff before telling the user to do a manual step

---

## Handoff Quality Checklist

A good handoff document answers all of these:
- [ ] Can a fresh Claude instance start the next task without reading any other file?
- [ ] Are all uncommitted changes documented?
- [ ] Are all decisions made this session recorded (not just the code result)?
- [ ] Are verification commands included to confirm the environment is in the expected state?
- [ ] If there's a Human SOP needed, is the exact resume message written?
