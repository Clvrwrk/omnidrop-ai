# Agent Teams — Master Reference Guide

Source: https://code.claude.com/docs/en/agent-teams
Requires: Claude Code v2.1.32+ with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

---

## What Agent Teams Are

Multiple Claude Code instances working together. One session is the **lead** — it creates the team, spawns teammates, manages the shared task list, and synthesizes results. Teammates are fully independent sessions with their own context windows that communicate directly with each other and the lead.

**Key difference from subagents:** Teammates message each other directly. Subagents only report back to the caller. Use agent teams when workers need to collaborate, not just execute.

---

## Enable (Already Done)

```json
// ~/.claude/settings.json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

---

## Architecture

| Component | Role |
|---|---|
| **Team lead** | Main session — creates team, spawns teammates, coordinates work |
| **Teammates** | Separate Claude Code instances, each owns assigned tasks |
| **Task list** | Shared work items with pending/in-progress/completed states + dependency tracking |
| **Mailbox** | Async messaging between agents (auto-delivered, no polling needed) |

**Storage locations:**
- Team config: `~/.claude/teams/{team-name}/config.json`
- Task list: `~/.claude/tasks/{team-name}/`
- Team config has a `members` array — teammates can read it to discover each other

---

## When to Use Agent Teams vs Alternatives

### Use agent teams when:
- Tasks can run **truly in parallel** with no file conflicts
- Teammates need to **challenge each other's findings** (debugging, research)
- Work spans independent layers (frontend / backend / tests)
- You need competing hypotheses investigated simultaneously

### Use subagents instead when:
- Workers are focused and only the result matters
- Sequential dependencies exist between tasks
- Token cost is a concern (subagents are cheaper)
- Same files are being edited

### Use git worktrees instead when:
- You want manual control of parallel sessions
- No automated coordination needed

---

## Subagents vs Agent Teams — Quick Reference

| | Subagents | Agent Teams |
|---|---|---|
| Context | Own window, results return to caller | Own window, fully independent |
| Communication | Report to main agent only | Direct teammate-to-teammate messaging |
| Coordination | Main agent manages all work | Shared task list, self-coordination |
| Best for | Focused tasks, result is all that matters | Collaboration, debate, cross-cutting work |
| Token cost | Lower | Higher (each teammate = full Claude instance) |

---

## Starting a Team

Just describe the task and team structure in natural language:

```text
Create an agent team with 3 teammates:
- One focused on [concern A]
- One focused on [concern B]
- One playing devil's advocate
```

Claude decides whether to create a team, or you can explicitly request one. Claude will not create a team without your approval.

---

## Display Modes

| Mode | How it works | Requirements |
|---|---|---|
| `in-process` | All teammates in main terminal, Shift+Down to cycle | Any terminal |
| `tmux` / split panes | Each teammate gets its own pane | tmux or iTerm2 |
| `auto` (default) | Split panes if already in tmux, otherwise in-process | — |

**Set globally** in `~/.claude.json`:
```json
{ "teammateMode": "in-process" }
```

**Set per session:**
```bash
claude --teammate-mode in-process
```

**In-process navigation:**
- `Shift+Down` — cycle through teammates (wraps back to lead after last)
- `Enter` — view a teammate's session
- `Escape` — interrupt current turn
- `Ctrl+T` — toggle task list

**Note:** Split-pane mode does NOT work in VS Code integrated terminal, Windows Terminal, or Ghostty.

---

## Controlling the Team

### Specify team size and models
```text
Create a team with 4 teammates. Use Sonnet for each teammate.
```

### Require plan approval before implementation
```text
Spawn an architect teammate to refactor the auth module.
Require plan approval before they make any changes.
```
Flow: teammate plans → sends approval request to lead → lead approves or rejects with feedback → if rejected, teammate revises → once approved, teammate implements.

The lead makes approval decisions autonomously. Shape its judgment in the prompt:
```text
Only approve plans that include test coverage. Reject plans that modify the DB schema.
```

### Talk to a teammate directly
In-process: `Shift+Down` to reach the teammate, then type. In split-pane: click the pane.

### Assign tasks
```text
Assign the auth refactor task to the security teammate
```
Or let teammates self-claim — after finishing, they pick the next unassigned, unblocked task automatically. File locking prevents race conditions.

### Shut down a teammate
```text
Ask the researcher teammate to shut down
```
Teammate can approve (graceful exit) or reject with explanation.

### Clean up the team
```text
Clean up the team
```
**Always use the lead to clean up.** Teammates running cleanup can leave resources in inconsistent state. Cleanup fails if active teammates are still running — shut them down first.

---

## Hooks for Quality Gates

| Hook | Fires when | Exit 2 effect |
|---|---|---|
| `TeammateIdle` | Teammate is about to go idle | Send feedback, keep teammate working |
| `TaskCreated` | A task is being created | Prevent creation, send feedback |
| `TaskCompleted` | A task is being marked complete | Prevent completion, send feedback |

Use these to enforce standards: require tests before marking complete, validate task descriptions, block low-quality work.

---

## Context & Communication Rules

- Teammates load: project `CLAUDE.md`, MCP servers, skills — same as a regular session
- Teammates do **NOT** inherit lead's conversation history
- Lead's conversation history does NOT carry over to teammates
- Messages are auto-delivered (no polling needed)
- When a teammate goes idle, it automatically notifies the lead
- `broadcast` = send to all teammates simultaneously — **use sparingly** (cost scales with team size)

---

## Permissions

- Teammates start with **lead's permission settings**
- If lead uses `--dangerously-skip-permissions`, all teammates do too
- Can change individual teammate modes after spawn — cannot set per-teammate modes at spawn time

---

## Team Size Guidelines

| Situation | Recommendation |
|---|---|
| Most workflows | 3–5 teammates |
| Tasks per teammate | 5–6 for optimal throughput |
| 15 independent tasks | 3 teammates is a good starting point |
| More than 5 teammates | Only if work genuinely benefits from parallelism |

Token cost scales **linearly** — each teammate is a full independent Claude instance.

---

## Task Sizing

- **Too small** → coordination overhead exceeds benefit
- **Too large** → teammates work too long without check-ins, wasted effort risk
- **Right size** → self-contained unit with a clear deliverable (a function, a test file, a review)

If the lead isn't creating enough tasks: `"Split the work into smaller pieces."`
If the lead starts doing work instead of delegating: `"Wait for your teammates to complete their tasks before proceeding."`

---

## Proven Prompting Patterns

### Parallel code review (clear role separation)
```text
Create an agent team to review PR #142. Spawn three reviewers:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```

### Competing hypotheses debugging (adversarial structure)
```text
Users report [symptom]. Spawn 5 agent teammates to investigate different
hypotheses. Have them talk to each other to disprove each other's theories,
like a scientific debate. Update the findings doc with whatever consensus emerges.
```

### Rich spawn prompt (always include task-specific context)
```text
Spawn a security reviewer teammate with the prompt:
"Review the authentication module at src/auth/ for security vulnerabilities.
Focus on token handling, session management, and input validation.
The app uses JWT tokens stored in httpOnly cookies.
Report any issues with severity ratings."
```

---

## Common Failure Modes & Fixes

| Problem | Fix |
|---|---|
| Teammates not appearing | Press Shift+Down — they may be running but not visible |
| Too many permission prompts | Pre-approve common operations in permission settings before spawning |
| Teammate stops on error | Navigate to it with Shift+Down, give direct instructions or spawn replacement |
| Lead shuts down before work is done | Tell it to keep going; tell it to wait for teammates |
| Task status lagging / blocked tasks | Check if work is done; manually update status or nudge via lead |
| Orphaned tmux sessions | `tmux ls` then `tmux kill-session -t <name>` |

---

## Known Limitations (Experimental)

- **No session resumption** — `/resume` and `/rewind` don't restore in-process teammates; lead may try to message teammates that no longer exist → spawn new ones
- **Task status can lag** — teammates sometimes fail to mark tasks complete, blocking dependents
- **Slow shutdown** — teammates finish current request before exiting
- **One team per session** — clean up before starting a new one
- **No nested teams** — teammates cannot spawn their own teams
- **Lead is fixed** — cannot promote a teammate to lead or transfer leadership
- **Split panes** — not supported in VS Code integrated terminal, Windows Terminal, or Ghostty

---

## CLAUDE.md Integration

`CLAUDE.md` works normally — teammates read it from their working directory. Use it to provide project-specific guidance that applies to all teammates automatically without repeating it in every spawn prompt.

---

## Quick Decision Checklist

Before creating an agent team, confirm:

- [ ] Tasks can run in parallel without file conflicts
- [ ] Each teammate has a clearly distinct role / domain
- [ ] Teammates benefit from communicating with each other (not just reporting results)
- [ ] Team size is 3–5 (not more unless genuinely warranted)
- [ ] Each task has a clear, self-contained deliverable
- [ ] Spawn prompts include sufficient task-specific context (not just "review this")
- [ ] Quality gate hooks are configured if standards need enforcing
- [ ] Lead will be monitored — don't let teams run fully unattended
