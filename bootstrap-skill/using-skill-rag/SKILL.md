---
name: using-skill-rag
description: Find relevant skills via RAG when a new task or topic starts; skip re-searching during interactive Q&A replies
---

# Skill RAG — Lazy Skill Loading

You have access to a skill corpus via MCP tools. Skills are NOT loaded into
your context by default. You search for them per **task**, not per message.

## When to search

**Parent agent**: call `mcp__skill-rag__search_skills(query=<the task>, k=5,
agent=<your harness name>)` when a **new task starts or the topic materially
shifts** — not on every user message. Pass your own harness as `agent` — e.g.
`"claude-code"`, `"codex"`, `"antigravity"`. Queries work in any language
(Korean and English both).

Concretely:

- **First substantive message of a task** → search.
- **Topic shifts** to something the current skill(s) don't cover → search again
  with the new task as the query.
- **Inside a sustained interactive flow** you already established (an
  interview, wizard, or Q&A-coaching role that runs many turns asking 1–3
  questions each) → **do NOT search again** when the user is merely answering
  your question (`"A"`, `"네"`, `"잘 모르겠어요"`, `"다음"`, `"이대로 마무리"`).
  The task context was fixed in the first turn; the reply can't need a new
  skill. Resume searching only when the user introduces a genuinely new task.

If you are unsure whether the topic shifted, searching once is fine — the cost
is one call. The rule exists to stop searching on every turn of a conversation
whose skill needs never change.

**Subagent**: When invoked, inspect the parent context you were given. If it
describes a substantive task (coding, design, debugging, etc.), call
`search_skills` with a query summarizing your task. If it's a narrow lookup the
parent already framed, skip.

## Handling responses

`search_skills` returns one of:

- `{status: "ok", hits: [{name, description, score}, ...]}`
  - Read each `description`. For any skill that clearly applies, call
    `mcp__skill-rag__get_skill(name)` to fetch its body. Then follow the
    skill exactly.
  - If multiple skills apply, fetch each. Process skills (brainstorming,
    debugging) before implementation skills.
  - If none of the descriptions actually fit despite being returned,
    proceed without a skill. Do not refetch with reworded queries.

- `{status: "no_match", hits: [], message: ...}`
  - No skill applies. Respond directly. **DO NOT call `search_skills` again
    for this turn with a rephrased query.**

- `{status: "skip", hits: [], message: ...}`
  - Your query was a bare reply inside an interactive flow, not a new task.
    Respond directly and **stop calling `search_skills` on every turn** of this
    conversation. Search again only when the user starts a new task.

`get_skill` returns one of:

- `{status: "ok", body: "..."}`
  - Follow the instructions in `body`.

- `{status: "not_found", message: ...}`
  - The skill was removed. **DO NOT call `get_skill` or `search_skills` for
    this name again this turn.** Proceed without it.

## Anti-patterns

- Searching again on every turn of an interview/wizard/Q&A flow whose task was
  already established. Search once per task, not once per message.
- Calling `search_skills` more than once for the same task with reworded
  queries to "try harder". One call. Trust the result.
- Calling `get_skill` for a skill whose description clearly doesn't fit
  just because it appeared in `hits`.
