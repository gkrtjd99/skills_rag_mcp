# MCP Interface

Two tools. Four terminal statuses across them.

## `search_skills(query: str, k: int = 5, agent: str | None = None) -> dict`

Find skills relevant to the query. Call when a new task starts or the topic
shifts, not on every reply inside an interactive flow. Auto-runs sync if the
cache is stale (skipped when the query is short-circuited as conversational).
`agent` names the calling harness (`"codex"`, `"claude-code"`, etc.) and is
currently informational. Each returned hit reports the source `agent` inferred
from its filesystem path.

`k` must be an integer from 1 through 50. Invalid values are rejected before
sync or retrieval; an `ok` response always contains at least one hit.

```json
// status: "ok"
{
  "status": "ok",
  "hits": [
    {
      "name": "code-review",
      "description": "Review code changes for bugs...",
      "score": 0.82,
      "agent": "codex"
    }
  ]
}

// status: "no_match"
{
  "status": "no_match",
  "hits": [],
  "message": "No skill matched this query. Proceed without using a skill."
}
```

```json
// status: "skip"
{
  "status": "skip",
  "hits": [],
  "message": "Query looks like a reply inside an interactive flow, not a new task. Skipped retrieval. Do not search again until the task or topic changes."
}
```

`no_match` covers an empty query, empty corpus, or candidates failing both
retrieval thresholds.

`skip` is returned **before** sync or embedding when the trimmed query is a bare
interactive-flow reply: a single alphabetic character (`A`/`B`/`C`/`D`), an
all-digit string, or an exact ko/en affirmation/ack token (`네`, `예`, `수정`,
`다음`, `잘 모르겠어요`, `yes`, `no`, `next`, `idk`, …). This costs no embedding
and signals the agent to stop searching every turn of a conversation. The match
is exact (case- and trailing-punctuation-insensitive), so a real query that
merely contains such a word is not skipped. See
`docs/superpowers/specs/2026-06-05-interactive-flow-skip.md`.

## Retrieval Contract

Search is hybrid:

- Dense: local sentence-transformers model
  (`intfloat/multilingual-e5-base` by default), cosine
  search in LanceDB over normalized `text`.
- Sparse: in-memory BM25 over the indexed `text` column. Tokenization preserves
  Latin/code identifiers and emits Hangul character bigrams.
- Keep rule: dense cosine >= `SCORE_THRESHOLD` (default 0.45) OR normalized
  BM25 >= `BM25_THRESHOLD` (default 0.30).
- Ordering: reciprocal rank fusion with `RRF_K` (default 60).

`text` is built from name, description, optional translated description, and
body. Translation is local ko<->en only and happens at index time for
added/changed records.

## `get_skill(name: str) -> dict`

Return the full `SKILL.md` body for a frontmatter skill name. The implementation
uses the index's `name -> path` mapping, so the directory name does not need to
match the frontmatter name. If the mapping is missing or stale, it forces sync
and retries once before returning `not_found`.

```json
// status: "ok"
{"status": "ok", "body": "---\nname: ...\n---\n..."}

// status: "not_found"
{
  "status": "not_found",
  "message": "Skill 'X' does not exist in the corpus. Do not call get_skill or search_skills for this name again. Proceed without it."
}
```

## Loop Prevention Contract

A conforming bootstrap skill must:

- Search per task, not per message: re-search only when a new task starts or
  the topic shifts, never on every reply inside a sustained interactive flow.
- On `search_skills -> no_match`: respond directly, not re-call with a
  reworded query.
- On `search_skills -> skip`: respond directly and stop searching every turn of
  this conversation; search again only when the user starts a new task.
- On `get_skill -> not_found`: not re-call `get_skill` or `search_skills` for
  the same name this turn.
- On `search_skills -> ok` where no description actually fits: proceed without
  a skill, not refetch.
