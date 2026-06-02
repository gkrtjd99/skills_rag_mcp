# Translation Retry State

Date: 2026-06-02
Status: Implemented

## Problem

When translation was enabled but MarianMT models were not cached, sync degraded
gracefully by indexing an empty translated description. Because unchanged rows
were skipped by content hash on later syncs, downloading the model later did
not automatically repair those rows.

## Decision

Add `translation_status` to the LanceDB schema:

- `ok`: translated text was stored.
- `failed`: translation was attempted but model load/run failed or returned
  empty text.
- `disabled`: translation was off at sync time.
- `skipped`: description was empty or had no translatable script.
- `pending`: default in memory before sync fills the field.

During sync, unchanged rows with `failed`, `disabled`, or `pending` status are
retried when translation is enabled and the description is translatable.

Schema migration: v5 -> v6 is handled as existing schema drift. The table is a
derived cache, so `open_table` drops and recreates it; sync rebuilds from the
corpus.

## Verification

- Translation tests cover status values.
- Index tests cover `translation_status` storage.
- Sync tests cover retrying a failed unchanged row.
- `uv run pytest tests/test_translate.py tests/test_index.py tests/test_sync.py -q`
- `uv run pytest -q`
