# Core Beliefs

Non-negotiable principles. Changes require explicit user buy-in.

## Local-First

No cloud APIs at index or query time by default. Embeddings, BM25,
translation, and MCP serving all run on the user's machine. Runtime model
loading defaults to the local cache only; first-time model downloads must be
explicit setup work, not a surprise side effect of a query.

One exception exists, approved by the maintainer on 2026-11-24 after a
held-out measurement: an opt-in rerank judge (`SKILL_RAG_RERANK=jev` or
`openai`, or a user-supplied provider) sends the query and the shortlisted
skills' names and descriptions to that provider's API for a fit judgment. It
must stay off by default, fall back to the local path on any failure, never
send skill bodies or paths, and never become a requirement for install, tests,
or indexing. A new built-in provider needs its own held-out measurement; any
other kind of cloud call needs the same explicit buy-in.

## Single Global Corpus

One canonical skill corpus: `~/.skills/<name>/SKILL.md`. Harness skills may be
collected into that corpus as symlinks, but retrieval and `get_skill` operate
against this one location and its derived index.

## Lazy Loading

The skill-rag path does not load all skills at session start. The bootstrap
skill calls `search_skills` per new task and calls `get_skill` only for skills
whose descriptions clearly fit the task. Native harness loading remains a
separate fallback and is not disabled by this repository.

## Single User

The project assumes one developer on one machine. Concurrency, sharing,
permissions, ACLs, and multi-tenant concerns are not designed for or tested.

## Measured Complexity Only

Complexity is allowed only after a measured retrieval or lifecycle failure.
Hybrid BM25, Korean normalization, agent attribution, and ko<->en description
translation exist because fixture or real-corpus failures justified them.

The opt-in judge rerank exists because the fixture-calibrated gate dropped to
recall@5 0.762 and no-match accuracy 0.533 on a held-out corpus
(`docs/benchmarks/2026-11-24-heldout-jev-rerank.md`).

Still out of scope: cloud embedding or translation providers, model-based
scoring on the default path, real-time filesystem watchers, multi-user
indexing, and speculative framework abstractions.

## Disposable Index

The LanceDB index is a cache derived from `~/.skills`. Schema drift can drop and
recreate it. Users should never treat `var/` as source data.
