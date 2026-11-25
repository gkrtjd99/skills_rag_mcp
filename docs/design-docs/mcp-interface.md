# MCP Interface

Two tools. Six terminal statuses across them.

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
      "score": 1.0,
      "agent": "codex"
    }
  ]
}

// status: "uncertain"
{
  "status": "uncertain",
  "hits": [
    {
      "name": "code-review",
      "description": "Review code changes for bugs...",
      "confidence": "low"
    }
  ],
  "message": "No skill was confirmed for this request. These are uncertain candidates: load one only if its description clearly covers the task; otherwise proceed without a skill."
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

`uncertain` hands the decision to the caller. Its hits carry no `score` and
no `agent`, only `"confidence": "low"`. It is returned in two cases:

- A judge is configured and no skill reaches its threshold: the single best
  skill at or above `SKILL_RAG_RERANK_UNCERTAIN_FROM` (default 0.7),
  description capped at 120 characters. A value at or above the rerank
  threshold turns this off.
- Opt-in, without a judge (or when the judge failed):
  `SKILL_RAG_LOCAL_CANDIDATES=3` returns the top 3 (capped by `k`) of the
  local ranking with descriptions capped at 300 characters, instead of the
  threshold gate's `ok` / `no_match`. Off by default.

The wording and shape were measured with a model acting as the caller
(`docs/benchmarks/2026-11-25-agent2-results.md`).

A skill the query names outright is returned as `ok` with `score` 1.0 before
any ranking or judgment, with or without a judge, and even if it was loaded
earlier in the session. A bare mention does not count, because skill names
are often ordinary words. The name must be the whole query, be written as a
command (`/name`, `$name`), or stand next to the word skill (`name skill`,
`name 스킬`, `skill name`, `스킬 name`). `SKILL_RAG_EXPLICIT=0` turns this
off.

`no_match` covers an empty query, an empty corpus, the local gate when
candidates fail both retrieval thresholds, and a judge that puts no skill at
or above the uncertain bound.

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
  (`intfloat/multilingual-e5-base` by default), with E5 `query:`/`passage:`
  prompts and cosine search in LanceDB over normalized `text`. Dense passages
  use name/description by default, while full bodies remain available to BM25;
  inputs are capped at 128 tokens by default so first indexing remains bounded
  on large corpora.
- Korean queries get a small local intent-vocabulary expansion before dense
  and sparse retrieval; no network translation is involved.
- Sparse: cached in-memory BM25 over the indexed `text` column. Tokenization
  preserves Latin/code identifiers, emits Hangul character bigrams, and
  ignores common query function words. A lexical rescue must cover at least
  half of the meaningful query terms.
- Keep rule: a dense hit must clear `SCORE_THRESHOLD` (default 0.78) and have
  at least one meaningful query-term match, unless it clears the higher
  dense-only confidence bar `DENSE_ONLY_THRESHOLD` (default 0.86) or is the
  clear top result with a `DENSE_ONLY_MARGIN_THRESHOLD` gap (default 0.05).
  A lexical rescue may independently pass when covered normalized BM25 >=
  `BM25_THRESHOLD` (default 0.30).
- Dense ranking uses a bounded shortlist (`max(k*4, 20)` by default); BM25
  still considers the complete corpus for exact lexical rescue.
- Ordering: reciprocal rank fusion with `RRF_K` (default 60). The returned
  `score` is the fused score normalized against the best hit for that query,
  so it follows response order, is bounded to `(0, 1]`, and is not comparable
  across unrelated queries. Dense and BM25 thresholds remain internal
  filtering signals.

### Opt-in rerank

With `SKILL_RAG_RERANK` set (`jev`, `openai`, or a custom
`package.module:factory`) the keep rule and ordering above are replaced. The
shortlist of `SKILL_RAG_RERANK_CANDIDATES` (default 16) is built by the
judge's scan of every skill when the corpus has at most
`SKILL_RAG_RERANK_SCAN_MAX` skills (default 500; `0` uses the fused rank
instead), and each shortlisted skill is judged for fit to the query.

In the default style (`SKILL_RAG_RERANK_STYLE=candidates`) every shortlisted
skill with probability >= `SKILL_RAG_RERANK_FLOOR` (default 0.5) is returned,
best first, at most `SKILL_RAG_RERANK_SHOWN` (default 8) of them:

```json
{
  "status": "candidates",
  "hits": [
    {"name": "code-review", "description": "Review code changes for bugs...", "score": 0.83}
  ],
  "message": "These are the closest skills, best first. Often none of them fits: load one only if its name and description clearly cover this task; otherwise proceed without a skill."
}
```

`score` is the judge's probability, descriptions are capped at
`SKILL_RAG_RERANK_DESCRIPTION_CHARS` (default 120), and `k` does not cap the
number shown. Nothing at or above the floor is `no_match`. The caller is
expected to load at most one, or none
(`docs/benchmarks/2026-11-25-candidates-results.md`).

The rest of this section describes `SKILL_RAG_RERANK_STYLE=single`. The
top `SKILL_RAG_RERANK_CANDIDATES` (default 16) by fused rank, with no
thresholds, are each judged by the configured model for fit to the query.
Candidates with probability >= `SKILL_RAG_RERANK_THRESHOLD` (default 0.9) are
kept in order of probability and at most `SKILL_RAG_RERANK_MAX_HITS` (default
1) are returned; none qualifying is `uncertain` (see above) or `no_match`. An
`ok` response under rerank therefore usually carries a single hit, and
`no_match` is common by design. Statuses and
hit fields are unchanged, with two differences in content: `score` is that
probability (comparable across queries, and no longer 1.0 for the first hit by
construction), and `description` is capped at
`SKILL_RAG_RERANK_DESCRIPTION_CHARS` (default 120) because the fit decision
has already been made. `skip`, empty-query, and empty-corpus responses never
trigger a request. On any failure the local result is returned. This sends the
query and the shortlisted names and descriptions to the judge's provider; see
`docs/superpowers/specs/2026-11-24-jev-rerank-opt-in.md`.

`text` is built from name, description, optional translated description, and
body. Translation is local ko<->en only, disabled by default, and happens at
index time for added/changed records when `SKILL_RAG_TRANSLATE=1`. Search hit
descriptions are capped at 280 characters by default to limit MCP context use.

A skill that `get_skill` already returned in the current session (one server
process) is left out of later `search_skills` results unless
`SKILL_RAG_EXCLUDE_LOADED=0`, so a follow-up search can return `no_match`
where the first one returned that skill.

## `get_skill(name: str) -> dict`

Return the full `SKILL.md` body for a frontmatter skill name. The implementation
uses the index's `name -> path` mapping, so the directory name does not need to
match the frontmatter name. If the mapping is missing or stale, it forces sync
and retries once before returning `not_found`. `path` is the directory that
holds the `SKILL.md`; files the body refers to (scripts, references, assets)
resolve relative to it. It matters most for adopted skills, which no harness
loads natively.

```json
// status: "ok"
{"status": "ok", "body": "---\nname: ...\n---\n...", "path": "/Users/me/.skills/code-review"}

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
