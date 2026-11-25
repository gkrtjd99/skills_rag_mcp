# Changelog

## [Unreleased]

### Added

- Opt-in second-stage rerank, `SKILL_RAG_RERANK`: a judge model returns the
  probability that each of the top 16 hybrid candidates fits the query. Off by
  default; falls back to the local gate on any failure.
  - `jev`: TypeSafe Jev (`rerank` extra, `TYPESAFE_API_KEY`).
  - `openai`: OpenAI Decisions API (`OPENAI_API_KEY`, no extra package).
  - `package.module:factory`: any model implementing `skill_rag.judges.Judge`.
  When on, the query plus shortlisted skill names and descriptions are sent to
  the chosen provider.
- Judged hits return descriptions capped at 120 characters
  (`SKILL_RAG_RERANK_DESCRIPTION_CHARS`), cutting the mean search response
  from 1,184 to about 235 characters on the held-out corpus.
- `bench/jev_rerank_ab.py` (one arm per `--judge`) and held-out query sets for
  measuring the gate and judges on a corpus the thresholds were not tuned on.
- `skill-rag status` reports rerank readiness and where data would be sent.
- Rerank is precision first: threshold 0.9 and at most one skill returned
  (`SKILL_RAG_RERANK_THRESHOLD`, `SKILL_RAG_RERANK_MAX_HITS`). On a fresh
  350-skill test set `jev` returns a skill that does not fit for 9.3% of
  requests with no matching skill (34.0% at the earlier 0.5 / up-to-`k`
  setting) and returns a useful skill for 67.9% of matching requests (79.6%).
- `search_skills` can answer `status: "uncertain"`: with a judge, when no
  skill reaches the threshold, the best one at or above
  `SKILL_RAG_RERANK_UNCERTAIN_FROM` (0.7) is returned marked
  `"confidence": "low"` and the calling agent decides. On a fresh test set a
  simulated agent loaded a useful skill for 67.0% of matching requests instead
  of 60.3%, and a wrong one for 8.2% of no-match requests instead of 4.1%.
  The bootstrap skill tells agents how to treat the new status.
- `SKILL_RAG_LOCAL_CANDIDATES` (off by default): without a judge, return the
  top N of the local ranking as uncertain candidates instead of the gate's
  hits. Fewer wrong loads, fewer useful ones.
- Optional whole-corpus scan by the judge (`SKILL_RAG_RERANK_SCAN_MAX`, off by
  default): finds the right skill more often and returns more wrong ones.
- `skill-rag adopt [names] [--from DIR]` moves skills out of harness or
  project skill directories into `~/.skills/`, so the harness stops loading
  their descriptions into every session; `skill-rag restore` moves them back.
  `uninstall` restores adopted skills first and never deletes one it cannot
  restore, even with `--purge`.
- `skill-rag install --no-collect` sets up the bootstrap skill and MCP
  registration without linking harness and plugin skills into the store.
- Local usage log (`var/usage.jsonl`, `SKILL_RAG_USAGE_LOG=stats|full|off`) of
  what was suggested and what was then loaded, and `skill-rag usage` to
  summarize it per skill. No request text unless `full`.
- Skills already loaded in the current session are no longer suggested again
  (`SKILL_RAG_EXCLUDE_LOADED`).
- `get_skill` also returns `path`, the skill's directory, so bundled scripts
  and references resolve for skills no harness loads natively.

### Measured

- Scale benchmark with the protocol committed before any data was fetched:
  433 skills from skills.sh, corpus sizes 50 to 350, 283 queries written by
  another model. Strict recall@1 at 50 / 350 skills: gate 0.619 / 0.450, `jev`
  0.862 / 0.672, `openai` 0.857 / 0.646. Strict no-match accuracy at 350:
  0.021, 0.266, 0.319. The first-stage shortlist holds the expected skill 96%
  of the time at 50 skills and 79% at 350. See
  `docs/benchmarks/2026-11-24-scale-results.md`.
- An earlier author-written set (45 skills, 133 queries) scored `jev` 0.979 /
  1.000 and `openai` 0.968 / 0.947; it is an upper bound on easy queries
  (`docs/benchmarks/2026-11-24-heldout-jev-rerank.md`).

### Changed

- Dense inputs default to 128 tokens with a 300-character body prefix (was 64
  and none); the index rebuilds itself on the next sync and indexing takes
  about twice as long. Fixture evaluations are unchanged at 1.000.
- `skill-rag query` follows the same search path as the MCP tool, including
  rerank when enabled.

## [0.3.0] - 2026-07-15

### Changed

- Use E5 `query:`/`passage:` prompts and schema v11 metadata so stale vector
  profiles rebuild automatically instead of being mixed with new queries.
- Limit dense passages to name and description by default, cap inputs at 64
  tokens, and retain the complete body for BM25 keyword rescue.
- Cache LanceDB metadata and BM25 structures between MCP calls and search a
  bounded dense shortlist while preserving full-corpus lexical rescue.
- Add deterministic Korean intent expansion and stricter meaningful-term
  coverage for multilingual matching and no-match decisions.
- Require lexical evidence or high dense confidence for dense-only matches,
  or a strong top-vs-runner-up margin in tiny corpora, preventing arbitrary
  nonsense queries from returning semantic false hits.
- Make local description translation opt-in with `SKILL_RAG_TRANSLATE=1`.
- Cap MCP hit descriptions at 280 characters and return a query-relative
  hybrid score aligned with the final RRF result order.

### Performance

- Reduce average dense indexing input from roughly 497 to 52 tokens on the
  1,925-skill corpus.
- Reduce the measured first search on a prepared real index from 51.2 seconds
  to 3.5 seconds, with subsequent searches at roughly 16.6 ms p95.
- On the actual 1,925-skill corpus, warm sequential p95 was 16.1 ms; 8, 16,
  and 32 concurrent workers measured 119.6 ms, 308.0 ms, and 540.2 ms p95
  respectively, without request errors.
- One hundred generated nonsense queries returned `no_match`; long-query and
  unchanged-sync checks completed without exceptions.
- Preserve recall@5 = 1.000, natural-language recall@1 = 1.000, and no-match
  accuracy = 1.000 on the repository evaluation fixtures.

### Fixed

- Prevent evaluator/sync clock tests from monkeypatching the process-wide
  `time.monotonic`, which could break LanceDB's background event loop.
- Keep generated indexes, benchmark output, and local model caches out of Git.

## [0.2.0] - 2026-07-14

### Changed

- Use `intfloat/multilingual-e5-base` as the default local embedding model.
- Keep `SKILL_RAG_MODEL` as an override for BGE-M3 or another compatible model.
- Rebuild a stale LanceDB cache automatically when the embedding dimension
  changes.
- Add disposable Docker model benchmarks and a bilingual natural-language
  evaluation fixture.
- Keep native Claude/Codex skill loading as a fallback; skill-rag remains a
  lazy MCP retrieval path rather than a native-loader replacement.

## [0.1.0] - Previous development baseline

- Initial local MCP RAG lifecycle, corpus collection, hybrid retrieval, and
  Claude/Codex bootstrap integration.
