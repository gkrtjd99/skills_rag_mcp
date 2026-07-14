# Changelog

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

### Fixed

- Prevent evaluator/sync clock tests from monkeypatching the process-wide
  `time.monotonic`, which could break LanceDB's background event loop.
- Keep generated indexes, benchmark output, and local model caches out of Git.

## [0.1.0] - Previous development baseline

- Initial local MCP RAG lifecycle, corpus collection, hybrid retrieval, and
  Claude/Codex bootstrap integration.
