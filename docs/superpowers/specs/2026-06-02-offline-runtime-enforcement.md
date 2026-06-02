# Offline Runtime Enforcement

Date: 2026-06-02
Status: Implemented

## Problem

`skill-rag eval` showed Hugging Face metadata HTTP requests while
`SKILL_RAG_LOCAL_FILES_ONLY=1` was active. Passing `local_files_only=True` to
sentence-transformers was not enough to enforce the project's no-cloud runtime
contract.

## Decision

Before importing sentence-transformers or transformers model loaders, force:

- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`

Only do this when `SKILL_RAG_LOCAL_FILES_ONLY` is enabled. Setup runs such as
`make install` still set `SKILL_RAG_LOCAL_FILES_ONLY=0` so first-time model
downloads remain explicit.

## Verification

- Unit tests cover the shared offline helper and both lazy model-load paths.
- `uv run pytest -q`
- `uv run skill-rag eval --json` should satisfy recall/latency without HTTP
  requests when models are already cached.
