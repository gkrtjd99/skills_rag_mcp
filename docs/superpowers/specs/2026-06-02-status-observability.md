# Status Observability

Date: 2026-06-02
Status: Implemented

## Problem

`skill-rag status` reported the dense threshold but omitted other runtime
settings that now materially affect retrieval and setup: BM25 threshold, RRF
constant, translation toggle, local-files-only mode, and embedding sequence
length.

## Decision

Extend both text and JSON status output with:

- `local_files_only`
- `max_seq_length`
- `bm25_threshold`
- `rrf_k`
- `translation_enabled`

Keep the existing `score_threshold` JSON key for compatibility, but label it as
"dense threshold" in human output.

Status must report `indexed_count` without creating the index table or loading
the embedding model.

## Verification

- CLI unit tests cover JSON keys and human output labels.
- Index and CLI tests cover the no-model-load count path.
- `uv run pytest tests/test_cli.py -q`
- `uv run pytest -q`
