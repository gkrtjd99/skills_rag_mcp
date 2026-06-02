# Status Observability Plan

Status: Implemented

## Steps

- [x] Add retrieval/runtime settings to the `status` payload.
- [x] Preserve the existing `score_threshold` JSON key.
- [x] Update human output labels for dense, BM25, RRF, translation, local-only,
  and max sequence length.
- [x] Count indexed rows without listing rows, creating tables, or loading the
  embedding model.
- [x] Add CLI tests for JSON and text output.
- [x] Run focused and full test suites.
