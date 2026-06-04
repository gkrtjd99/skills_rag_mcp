# Interactive-Flow Skip

Date: 2026-06-05
Status: Implemented

## Problem

The bootstrap meta-skill instructs the agent to call `search_skills` *before
responding to any user message*. That rule is correct for one-shot task
requests, but it misfires inside **sustained interactive flows** — interview,
wizard, or Q&A-coaching prompts (e.g. a PRD coach that walks the user through
12 sections, asking 1–3 questions per turn).

In such a flow:

- The task context is fixed once, in the first turn, when the agent adopts the
  role.
- Every later user message is just an answer to the assistant's own question
  ("A", "네", "잘 모르겠어요", "다음").
- Those answers carry no new skill signal, yet each one triggers a full
  embedding + hybrid search (and sometimes a `get_skill`).

Over a dozen interview turns this wastes latency and burns context on tool
round-trips that can never change the answer. The user wants per-**context**
retrieval (search when a new task/topic arises) — not per-**message**
retrieval — and explicit skipping inside interactive Q&A.

## Options Considered

### Option 1 — Reframe the bootstrap contract (prompt-only)

Rewrite the meta-skill so the rule is "search at the **start of a new task or
when the topic materially shifts**", and explicitly skip re-searching during a
sustained interactive flow the agent already established.

- **Pros:** Zero code, zero false-positive risk, portable across every harness
  (Claude Code, Codex, …) because the meta-skill text is the one instruction
  every harness reliably loads. Directly matches the user's mental model.
- **Cons:** Agent-judged, not enforced. A model that ignores the guidance keeps
  searching.

### Option 2 — Server-side low-information guard (code)

`search_skills` cheaply detects conversational / low-information queries
(single multiple-choice letters, bare numbers, ko/en yes-no-ack tokens) and
returns a new `skip` status **before** loading the embedding model or running
the vector search.

- **Pros:** Enforced and cheap — kills the embedding + search cost on those
  turns even if the agent still calls the tool. The `skip` message reinforces
  the interactive-flow rule. Fully testable.
- **Cons:** The tool round-trip still costs some context (it does not eliminate
  the call). The heuristic could, in theory, misfire on a rare legitimate
  one-word query; the cost of a misfire is only "proceed without a skill".

### Option 3 — Explicit mode tool / server session state (code)

Add `set_search_mode("interactive" | "active")`; the agent flips to interactive
when it enters an interview and `search_skills` short-circuits while it holds.

- **Pros:** Unambiguous, no query-text guessing.
- **Cons:** MCP cross-call state is fragile (multiple clients, server restarts,
  no per-conversation key). The agent must remember to flip *both* directions or
  it gets stuck. Largest surface area for the least marginal gain over Options
  1+2.

### Option 4 — Harness hook / settings gate (out of scope)

Suppress retrieval from a Claude Code Stop/PreToolUse hook.

- **Rejected:** Non-portable (Codex has no equivalent) and couples a
  harness-agnostic product to one harness.

## Decision

Ship **Option 1 (primary) + Option 2 (defense-in-depth)**.

- Option 1 reframes the contract so the agent stops searching every turn inside
  an interactive flow — this is the lever that actually removes the calls and
  matches what the user asked for.
- Option 2 is the enforced safety net: when the agent *does* call on a trivial
  reply, the call is cheap (no embedding, no search) and the `skip` status nudges
  it back onto the per-task rule.

Reject Option 3 (fragile state, low marginal value) and Option 4 (non-portable).

## Behavior

`search_skills` gains a fourth terminal status, `skip`:

```json
{
  "status": "skip",
  "hits": [],
  "message": "Query looks like a reply inside an interactive flow, not a new task. Skipped retrieval. Do not search again until the task or topic changes."
}
```

A query is treated as conversational (→ `skip`) when its trimmed form is:

- a single alphabetic character (a multiple-choice answer: `A`/`B`/`C`/`D`), or
- only digits (a numbered choice or progress answer), or
- an exact match, case- and trailing-punctuation-insensitive, of a curated
  ko/en affirmation / negation / acknowledgement set (`네`, `예`, `아니요`,
  `좋아요`, `수정`, `다음`, `잘 모르겠어요`, `yes`, `no`, `ok`, `next`,
  `idk`, …).

Empty queries keep returning `no_match` (unchanged). The guard runs *before*
`sync_if_stale` and before any embedding work.

## Verification

- Unit tests: `is_conversational` true/false table; `search_skills` returns
  `skip` for conversational input without touching the index; real queries still
  return `ok`/`no_match`.
- The bootstrap meta-skill documents `skip` alongside `ok`/`no_match`/
  `not_found` and states the per-task (not per-message) rule.
- `uv run pytest -q`
