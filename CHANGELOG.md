# Changelog

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
